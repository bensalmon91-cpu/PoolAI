# PoolAI Brain - Backup to iCloud
# Compresses the local database and syncs to iCloud for cloud storage
# Keeps last 3 backups to manage space

$ErrorActionPreference = "Stop"

# Paths (resolved relative to this script so it's portable)
$LocalBrain = $PSScriptRoot
$LocalDB = "$LocalBrain\output\pool_readings.db"
$iCloudBackup = "C:\Users\bensa\iCloudDrive\MBSoftware\PoolAI_Backups"
$LogFile = "$LocalBrain\backup.log"
$MaxBackups = 3

function Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Tee-Object -FilePath $LogFile -Append
}

Log "=========================================="
Log "PoolAI Brain Backup Starting"
Log "=========================================="

# Create backup directory if needed
if (-not (Test-Path $iCloudBackup)) {
    New-Item -ItemType Directory -Path $iCloudBackup -Force | Out-Null
    Log "Created backup directory: $iCloudBackup"
}

# Check if DB exists
if (-not (Test-Path $LocalDB)) {
    Log "ERROR: Database not found at $LocalDB"
    exit 1
}

# Get DB size
$dbSize = (Get-Item $LocalDB).Length / 1GB
Log "Database size: $([math]::Round($dbSize, 2)) GB"

# Create timestamped backup filename
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupName = "pool_readings_$timestamp.db.gz"
$backupPath = "$iCloudBackup\$backupName"
$tempGz = "$env:TEMP\$backupName"

Log "Creating compressed backup..."

try {
    # Use .NET GZip compression
    $sourceStream = [System.IO.File]::OpenRead($LocalDB)
    $destStream = [System.IO.File]::Create($tempGz)
    $gzipStream = New-Object System.IO.Compression.GZipStream($destStream, [System.IO.Compression.CompressionLevel]::Optimal)

    $buffer = New-Object byte[] 65536
    $totalRead = 0
    $dbSizeBytes = (Get-Item $LocalDB).Length

    while (($read = $sourceStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
        $gzipStream.Write($buffer, 0, $read)
        $totalRead += $read
        $percent = [math]::Round(($totalRead / $dbSizeBytes) * 100, 0)
        Write-Progress -Activity "Compressing database" -PercentComplete $percent
    }

    $gzipStream.Close()
    $destStream.Close()
    $sourceStream.Close()

    $compressedSize = (Get-Item $tempGz).Length / 1GB
    Log "Compressed size: $([math]::Round($compressedSize, 2)) GB (ratio: $([math]::Round($dbSize / $compressedSize, 1))x)"

    # Move to iCloud
    Log "Copying to iCloud..."
    Move-Item -Path $tempGz -Destination $backupPath -Force
    Log "Backup saved: $backupName"

} catch {
    Log "ERROR: Compression failed - $_"
    if (Test-Path $tempGz) { Remove-Item $tempGz -Force }
    exit 1
}

# Clean up old backups (keep last N)
Log "Cleaning up old backups (keeping last $MaxBackups)..."
$backups = Get-ChildItem -Path $iCloudBackup -Filter "pool_readings_*.db.gz" | Sort-Object LastWriteTime -Descending

if ($backups.Count -gt $MaxBackups) {
    $toDelete = $backups | Select-Object -Skip $MaxBackups
    foreach ($old in $toDelete) {
        Remove-Item $old.FullName -Force
        Log "  Removed old backup: $($old.Name)"
    }
}

# Show current backups
Log "Current backups:"
Get-ChildItem -Path $iCloudBackup -Filter "pool_readings_*.db.gz" | ForEach-Object {
    $sizeMB = [math]::Round($_.Length / 1MB, 1)
    Log "  $($_.Name) - $sizeMB MB"
}

Log "=========================================="
Log "Backup complete!"
Log "=========================================="
