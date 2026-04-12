# PoolAIssistant Update Packager
# Creates a tar.gz package for software updates
# Run from: PoolDash_v6 folder

param(
    [string]$Version = ""
)

# Save the starting directory (absolute path)
$StartDir = (Get-Location).Path

# Get version from VERSION file if not specified
if (-not $Version) {
    if (Test-Path "VERSION") {
        $Version = (Get-Content "VERSION" -Raw).Trim()
    } else {
        Write-Host "ERROR: No version specified and no VERSION file found" -ForegroundColor Red
        Write-Host "Usage: .\package_update.ps1 -Version 6.2.1"
        exit 1
    }
}

Write-Host "=== PoolAIssistant Update Packager ===" -ForegroundColor Cyan
Write-Host "Version: $Version"
Write-Host ""

# Output filename - use ABSOLUTE paths
$OutputDir = Join-Path $StartDir "releases"
$OutputFile = "update-v$Version.tar.gz"
$OutputPath = Join-Path $OutputDir $OutputFile

# Create releases directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Write-Host "Created: $OutputDir"
}

# Files/folders to include in the update
$IncludeItems = @(
    "pooldash_app",
    "scripts",
    "docs",
    "VERSION",
    "requirements.txt"
)

# Files to exclude
$ExcludePatterns = @(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".env",
    "*.sqlite3",
    "instance",
    "releases",
    "tools"
)

Write-Host "Creating package..." -ForegroundColor Yellow

# Create temp directory for staging
$TempDir = Join-Path $env:TEMP "poolaissistant_package_$Version"
if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Copy files to temp directory
foreach ($item in $IncludeItems) {
    $sourcePath = Join-Path $StartDir $item
    if (Test-Path $sourcePath) {
        Write-Host "  Adding: $item"
        if ((Get-Item $sourcePath).PSIsContainer) {
            # It's a directory - copy recursively
            $dest = Join-Path $TempDir $item
            Copy-Item -Path $sourcePath -Destination $dest -Recurse -Force

            # Remove excluded patterns
            foreach ($pattern in $ExcludePatterns) {
                Get-ChildItem -Path $dest -Recurse -Include $pattern -Force -ErrorAction SilentlyContinue |
                    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            }
        } else {
            # It's a file
            Copy-Item -Path $sourcePath -Destination $TempDir -Force
        }
    } else {
        Write-Host "  Skipping (not found): $item" -ForegroundColor DarkGray
    }
}

# Create tar.gz using tar (available in Windows 10+)
Write-Host ""
Write-Host "Compressing to: $OutputPath" -ForegroundColor Yellow

# Change to temp dir and create archive with ABSOLUTE output path
Push-Location $TempDir
try {
    # Use absolute path for output
    tar -czf "$OutputPath" *
    if ($LASTEXITCODE -ne 0) {
        throw "tar command failed with exit code $LASTEXITCODE"
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Pop-Location
    Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    exit 1
} finally {
    Pop-Location
}

# Cleanup temp directory
Remove-Item -Recurse -Force $TempDir

# Verify output exists
if (-not (Test-Path $OutputPath)) {
    Write-Host "ERROR: Package was not created!" -ForegroundColor Red
    exit 1
}

# Calculate checksum
$hash = (Get-FileHash -Path $OutputPath -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $OutputPath).Length
$sizeMB = [math]::Round($size / 1MB, 2)

Write-Host ""
Write-Host "=== Package Created ===" -ForegroundColor Green
Write-Host "File:     $OutputPath"
Write-Host "Size:     $sizeMB MB ($size bytes)"
Write-Host "SHA256:   $hash"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Go to: https://poolaissistant.modprojects.co.uk/admin/updates.php"
Write-Host "2. Enter version: $Version"
Write-Host "3. Upload file: $OutputPath"
Write-Host "4. Pi will auto-update at 3 AM, or trigger manually"
