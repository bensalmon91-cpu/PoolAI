# First check if we can reach the network at all
Write-Host "Scanning 192.168.2.1-254 for SSH (port 22)..."
Write-Host "Using 500ms timeout per host..."
Write-Host ""

$results = @()
$count = 0
1..254 | ForEach-Object {
    $count++
    if ($count % 50 -eq 0) { Write-Host "Progress: $count/254 IPs scanned..." }

    $ip = "192.168.2.$_"
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $tcp.BeginConnect($ip, 22, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne(500)
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
if ($results.Count -eq 0) {
    Write-Host "No devices with SSH open found on 192.168.2.x"
} else {
    Write-Host "Devices with SSH open:"
    $results | ForEach-Object { Write-Host "  $_" }
}
