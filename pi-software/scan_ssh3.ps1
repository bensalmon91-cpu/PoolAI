# Scan using the Ethernet interface (192.168.2.10)
Write-Host "Scanning 192.168.2.1-254 for SSH (port 22)..."
Write-Host "Local IP: 192.168.2.10 (Ethernet interface)"
Write-Host "Using 1000ms timeout per host..."
Write-Host ""

$results = @()
$pingable = @()
$count = 0

# First do a quick ping sweep to find live hosts
Write-Host "Phase 1: Quick ping sweep..."
1..254 | ForEach-Object {
    $ip = "192.168.2.$_"
    $ping = Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1
    if ($ping) {
        Write-Host "  PING: $ip is alive"
        $pingable += $ip
    }
}

Write-Host ""
Write-Host "Phase 2: SSH port scan on live hosts..."

# Now scan SSH on all IPs anyway (some might block ping but have SSH open)
1..254 | ForEach-Object {
    $count++
    if ($count % 50 -eq 0) { Write-Host "Progress: $count/254 IPs scanned..." }

    $ip = "192.168.2.$_"
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $tcp.BeginConnect($ip, 22, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne(1000)
        if ($wait -and $tcp.Connected) {
            Write-Host "FOUND: $ip - SSH OPEN"
            $results += $ip
        }
        $tcp.Close()
    } catch {
        $tcp.Close()
    }
}

Write-Host ""
Write-Host "=== SCAN COMPLETE ==="
Write-Host "Hosts responding to ping: $($pingable.Count)"
$pingable | ForEach-Object { Write-Host "  $_" }
Write-Host ""
if ($results.Count -eq 0) {
    Write-Host "No devices with SSH (port 22) open found"
} else {
    Write-Host "Devices with SSH (port 22) open:"
    $results | ForEach-Object { Write-Host "  $_" }
}
