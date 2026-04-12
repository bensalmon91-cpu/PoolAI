$results = @()
1..254 | ForEach-Object {
    $ip = "192.168.2.$_"
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $tcp.BeginConnect($ip, 22, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne(300)
        if ($wait -and $tcp.Connected) {
            $results += $ip
        }
        $tcp.Close()
    } catch {}
}
$results | ForEach-Object { Write-Host "$_ - SSH OPEN" }
