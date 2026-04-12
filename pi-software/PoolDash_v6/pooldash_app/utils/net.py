import socket
import subprocess
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

def tcp_connect_ok(host: str, port: int, timeout_s: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, None
    except Exception as e:
        return False, str(e)


def validate_ip(ip: str) -> Tuple[bool, str]:
    """
    Validate an IP address format.
    Returns (is_valid, error_message).
    """
    if not ip:
        return False, "IP address is required"

    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip.strip())
    if not match:
        return False, "Invalid IP address format (expected: x.x.x.x)"

    octets = [int(g) for g in match.groups()]
    if any(o < 0 or o > 255 for o in octets):
        return False, "Invalid IP address: each number must be 0-255"

    if octets[0] == 0:
        return False, "Invalid IP address: cannot start with 0"
    if octets[0] == 127:
        return False, "Invalid IP address: 127.x.x.x is loopback"
    if octets == [255, 255, 255, 255]:
        return False, "Invalid IP address: broadcast address"

    return True, ""


def calculate_pi_ip(controller_ip: str) -> Tuple[str, str, str]:
    """
    Given controller IP, calculate appropriate Pi IP on same subnet.
    Returns (pi_ip, netmask, gateway).

    Example: controller 192.168.200.11 -> Pi 192.168.200.100
    """
    valid, err = validate_ip(controller_ip)
    if not valid:
        return "", "", err

    parts = controller_ip.strip().split('.')
    last_octet = int(parts[3])

    # Use .100 for Pi unless controller is .100, then use .101
    pi_last_octet = 100 if last_octet != 100 else 101

    pi_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{pi_last_octet}"
    netmask = "24"  # /24 is standard for most controller networks
    gateway = f"{parts[0]}.{parts[1]}.{parts[2]}.1"  # Common gateway

    return pi_ip, netmask, gateway


def check_ethernet_cable() -> Dict:
    """
    Check if ethernet cable is physically connected to eth0.
    Returns dict with status info.
    """
    result = {
        "connected": False,
        "carrier": False,
        "operstate": "unknown",
        "message": "Unknown status"
    }

    try:
        # Check carrier (1 = cable connected, 0 = not connected)
        carrier_path = "/sys/class/net/eth0/carrier"
        operstate_path = "/sys/class/net/eth0/operstate"

        try:
            with open(carrier_path, 'r') as f:
                carrier = f.read().strip()
                result["carrier"] = carrier == "1"
        except (FileNotFoundError, IOError):
            # If carrier file doesn't exist, interface may be down
            result["carrier"] = False

        try:
            with open(operstate_path, 'r') as f:
                operstate = f.read().strip()
                result["operstate"] = operstate
        except (FileNotFoundError, IOError):
            result["operstate"] = "unknown"

        # Determine overall connected status
        if result["carrier"]:
            result["connected"] = True
            result["message"] = "Ethernet cable connected"
        elif result["operstate"] == "down":
            result["connected"] = False
            result["message"] = "Ethernet cable not connected"
        elif result["operstate"] == "up" and not result["carrier"]:
            result["connected"] = False
            result["message"] = "Ethernet cable not connected (no carrier)"
        else:
            result["connected"] = False
            result["message"] = f"Ethernet status: {result['operstate']}"

    except Exception as e:
        result["message"] = f"Error checking ethernet: {e}"

    return result


def ping_host(host: str, timeout_s: float = 2.0) -> Tuple[bool, str]:
    """
    Ping a host to check if it's reachable.
    Returns (reachable, message).
    """
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(int(timeout_s)), host],
            capture_output=True,
            text=True,
            timeout=timeout_s + 1
        )
        if result.returncode == 0:
            return True, "Host is reachable"
        else:
            return False, "Host did not respond to ping"
    except subprocess.TimeoutExpired:
        return False, "Ping timed out"
    except FileNotFoundError:
        return False, "Ping command not available"
    except Exception as e:
        return False, str(e)


def check_ip_available(ip: str, timeout_s: float = 1.0) -> Tuple[bool, str]:
    """
    Check if an IP address is available (not in use).
    Returns (available, message).
    """
    reachable, _ = ping_host(ip, timeout_s)
    if reachable:
        return False, f"IP {ip} is already in use by another device"
    return True, f"IP {ip} appears to be available"


def get_current_eth0_config() -> Dict:
    """
    Get current eth0 configuration for backup purposes.
    """
    config = {
        "ip": "",
        "netmask": "24",
        "gateway": "",
        "mode": "unknown"
    }

    try:
        # Get current IP
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", "eth0"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    ip_cidr = parts[i + 1]
                    if "/" in ip_cidr:
                        config["ip"], config["netmask"] = ip_cidr.split("/")
                    else:
                        config["ip"] = ip_cidr
                    break

        # Get gateway
        gw_result = subprocess.run(
            ["ip", "route", "show", "default", "dev", "eth0"],
            capture_output=True, text=True, timeout=5
        )
        if gw_result.returncode == 0 and gw_result.stdout.strip():
            parts = gw_result.stdout.split()
            for i, p in enumerate(parts):
                if p == "via" and i + 1 < len(parts):
                    config["gateway"] = parts[i + 1]
                    break

        # Try to detect mode
        nmcli_result = subprocess.run(
            ["nmcli", "-t", "-f", "ipv4.method", "con", "show", "--active"],
            capture_output=True, text=True, timeout=5
        )
        if "manual" in nmcli_result.stdout:
            config["mode"] = "static"
        elif "auto" in nmcli_result.stdout:
            config["mode"] = "dhcp"

    except Exception:
        pass

    return config


def friendly_error_message(error: str) -> str:
    """
    Convert technical network errors to user-friendly messages.
    """
    error = str(error).lower()

    if "no-carrier" in error or "no carrier" in error:
        return "Ethernet cable not connected"
    if "connection refused" in error:
        return "Controller not responding - is it powered on?"
    if "network unreachable" in error or "network is unreachable" in error:
        return "Can't reach controller - checking network settings..."
    if "ehostunreach" in error or "host unreachable" in error:
        return "Controller is on a different network"
    if "timed out" in error or "timeout" in error:
        return "Connection timed out - controller may be offline"
    if "no route" in error:
        return "No network route to controller"

    return error


def scan_specific_subnet(
    subnet: str,
    port: int = 502,
    timeout_s: float = 0.5,
    max_workers: int = 50
) -> Dict:
    """
    Scan a specific subnet for Modbus devices.
    Subnet can be "192.168.200" or "192.168.200.0/24".
    """
    # Normalize subnet format
    subnet = subnet.strip()
    if not "/" in subnet:
        # Convert "192.168.200" to "192.168.200.0/24"
        parts = subnet.split(".")
        if len(parts) == 3:
            subnet = f"{subnet}.0/24"
        elif len(parts) == 4:
            subnet = f"{subnet}/24"

    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid subnet: {e}",
            "devices": []
        }

    # Skip very large subnets
    if network.prefixlen < 16:
        return {
            "success": False,
            "error": "Subnet too large (smaller than /16)",
            "devices": []
        }

    found = scan_subnet_for_modbus(
        network=network,
        port=port,
        timeout_s=timeout_s,
        max_workers=max_workers
    )

    return {
        "success": True,
        "network": str(network),
        "devices_found": len(found),
        "devices": found
    }


def get_local_subnets() -> List[Dict]:
    """
    Get local network interfaces and their subnets.
    Returns list of dicts with 'interface', 'ip', 'network' keys.
    """
    subnets = []
    try:
        # Use ip command to get interfaces with IPv4 addresses
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            # Format: "2: eth0    inet 192.168.1.100/24 brd 192.168.1.255 scope global eth0"
            parts = line.split()
            if len(parts) >= 4:
                iface = parts[1].rstrip(':')
                for i, p in enumerate(parts):
                    if p == "inet" and i + 1 < len(parts):
                        addr_cidr = parts[i + 1]
                        try:
                            interface = ipaddress.IPv4Interface(addr_cidr)
                            # Skip loopback and link-local
                            if interface.ip.is_loopback or interface.ip.is_link_local:
                                continue
                            subnets.append({
                                'interface': iface,
                                'ip': str(interface.ip),
                                'network': interface.network,
                            })
                        except Exception:
                            pass
                        break
    except Exception:
        pass
    return subnets


def scan_port(host: str, port: int, timeout_s: float = 0.5) -> Optional[str]:
    """
    Check if a port is open on a host.
    Returns the host IP if open, None otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return host
    except Exception:
        return None


def scan_subnet_for_modbus(
    network: ipaddress.IPv4Network = None,
    port: int = 502,
    timeout_s: float = 0.5,
    max_workers: int = 50,
    skip_ips: List[str] = None,
    progress_callback=None
) -> List[Dict]:
    """
    Scan a subnet for devices with Modbus port open.

    Args:
        network: IPv4Network to scan (e.g., 192.168.1.0/24)
        port: Port to scan (default 502 for Modbus)
        timeout_s: Timeout per connection attempt
        max_workers: Number of parallel scan threads
        skip_ips: List of IPs to skip (e.g., local IP)
        progress_callback: Optional callback(scanned, total) for progress updates

    Returns:
        List of dicts with 'ip', 'port', 'responding' keys
    """
    if network is None:
        return []

    skip_ips = set(skip_ips or [])
    hosts_to_scan = [
        str(ip) for ip in network.hosts()
        if str(ip) not in skip_ips
    ]

    total = len(hosts_to_scan)
    found = []
    scanned = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scan_port, host, port, timeout_s): host
            for host in hosts_to_scan
        }

        for future in as_completed(futures):
            scanned += 1
            if progress_callback and scanned % 10 == 0:
                progress_callback(scanned, total)

            result = future.result()
            if result:
                found.append({
                    'ip': result,
                    'port': port,
                    'responding': True
                })

    return found


def scan_all_subnets_for_modbus(
    port: int = 502,
    timeout_s: float = 0.5,
    max_workers: int = 50
) -> Dict:
    """
    Scan all local subnets for Modbus devices.

    Returns:
        Dict with 'subnets_scanned', 'devices_found', 'devices' keys
    """
    subnets = get_local_subnets()
    all_found = []
    subnets_info = []

    # Collect all local IPs to skip
    local_ips = [s['ip'] for s in subnets]

    for subnet in subnets:
        network = subnet['network']
        # Skip very large subnets (larger than /16)
        if network.prefixlen < 16:
            continue

        # For /24 and smaller, scan all hosts
        # For larger subnets, limit to first 254 hosts
        if network.prefixlen >= 24:
            found = scan_subnet_for_modbus(
                network=network,
                port=port,
                timeout_s=timeout_s,
                max_workers=max_workers,
                skip_ips=local_ips
            )
        else:
            # For larger subnets, scan common ranges
            # e.g., x.x.1.1-254, x.x.2.1-254, etc.
            found = []
            base = network.network_address
            for third_octet in range(1, 5):  # Scan first 4 /24 ranges
                try:
                    small_net = ipaddress.IPv4Network(f"{base + (third_octet * 256)}/24")
                    found.extend(scan_subnet_for_modbus(
                        network=small_net,
                        port=port,
                        timeout_s=timeout_s,
                        max_workers=max_workers,
                        skip_ips=local_ips
                    ))
                except Exception:
                    pass

        subnets_info.append({
            'interface': subnet['interface'],
            'network': str(network),
            'devices_found': len(found)
        })
        all_found.extend(found)

    # Remove duplicates (same device might be found via different interfaces)
    seen = set()
    unique = []
    for d in all_found:
        if d['ip'] not in seen:
            seen.add(d['ip'])
            unique.append(d)

    return {
        'subnets_scanned': subnets_info,
        'devices_found': len(unique),
        'devices': unique
    }


def test_modbus_connection(host: str, port: int = 502, timeout_s: float = 2.0) -> Dict:
    """
    Test if a host responds to Modbus requests.
    Tries to read holding registers to confirm it's a Modbus device.

    Returns:
        Dict with 'ip', 'port', 'modbus_ok', 'error' keys
    """
    result = {
        'ip': host,
        'port': port,
        'modbus_ok': False,
        'error': None
    }

    try:
        # Try to import pymodbus for actual Modbus test
        from pymodbus.client import ModbusTcpClient

        client = ModbusTcpClient(host, port=port, timeout=timeout_s)
        if client.connect():
            try:
                # Try reading a holding register (common test)
                response = client.read_holding_registers(0, 1, slave=1)
                if not response.isError():
                    result['modbus_ok'] = True
                else:
                    # Even an error response means Modbus is working
                    result['modbus_ok'] = True
                    result['error'] = 'Modbus responded with error (normal for some devices)'
            except Exception as e:
                result['error'] = str(e)
            finally:
                client.close()
        else:
            result['error'] = 'Could not connect'
    except ImportError:
        # pymodbus not available, just report port is open
        ok, err = tcp_connect_ok(host, port, timeout_s)
        result['modbus_ok'] = ok
        if not ok:
            result['error'] = err
        else:
            result['error'] = 'Port open (pymodbus not available for full test)'
    except Exception as e:
        result['error'] = str(e)

    return result
