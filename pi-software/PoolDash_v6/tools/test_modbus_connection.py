#!/usr/bin/env python3
"""
Quick Modbus connection test utility
Tests connectivity to configured pool controllers before starting logger
"""
import json
import os
import sys
from pymodbus.client import ModbusTcpClient


def load_controllers():
    """Load controller configuration from settings"""
    settings_path = os.getenv("POOLDASH_SETTINGS_PATH", "")
    if not settings_path:
        settings_path = os.path.join(os.path.dirname(__file__), "instance", "pooldash_settings.json")

    if not os.path.exists(settings_path):
        print(f"Settings file not found: {settings_path}")
        return []

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        controllers = data.get("controllers", [])
        return [c for c in controllers if c.get("enabled")]
    except Exception as e:
        print(f"Error loading settings: {e}")
        return []


def test_connection(host, port=502, unit=1):
    """Test Modbus TCP connection to a controller"""
    print(f"\nTesting {host}:{port} (unit {unit})...")

    try:
        client = ModbusTcpClient(host=host, port=port, timeout=3)

        if not client.connect():
            print(f"  ❌ Connection failed")
            return False

        print(f"  ✓ Connected successfully")

        # Try reading a single register to verify communication
        try:
            result = client.read_holding_registers(address=0, count=1, unit=unit)
            if result and not result.isError():
                print(f"  ✓ Modbus communication OK")
                success = True
            else:
                print(f"  ⚠ Connected but Modbus read failed (check unit ID)")
                success = False
        except Exception as e:
            print(f"  ⚠ Connected but Modbus test failed: {e}")
            success = False

        client.close()
        return success

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    """Test all configured controllers"""
    print("=" * 60)
    print("PoolAIssistant - Modbus Connection Test")
    print("=" * 60)

    controllers = load_controllers()

    if not controllers:
        print("\n⚠ No controllers configured")
        print("Configure controllers in Settings UI or edit:")
        print("  instance/pooldash_settings.json")
        return 1

    print(f"\nFound {len(controllers)} enabled controller(s)")

    results = []
    for ctrl in controllers:
        host = ctrl.get("host")
        name = ctrl.get("name", host)
        port = ctrl.get("port", 502)
        unit = ctrl.get("unit", 1)

        print(f"\n[{name}]")
        success = test_connection(host, port, unit)
        results.append((name, success))

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    for name, success in results:
        status = "✓ OK" if success else "❌ FAILED"
        print(f"  {name}: {status}")

    all_ok = all(success for _, success in results)

    if all_ok:
        print("\n✓ All controllers reachable")
        return 0
    else:
        print("\n❌ Some controllers failed - check network/configuration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
