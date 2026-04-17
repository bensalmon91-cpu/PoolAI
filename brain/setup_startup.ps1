# PoolAIssistant Brain - Windows Startup Setup Script
# Run this script as Administrator to register the sync task

param(
    [switch]$Remove,
    [switch]$RunNow
)

$TaskName = "PoolAIssistant_BrainSync"
$ScriptPath = Join-Path $PSScriptRoot "run_sync.bat"
$Description = "Syncs PoolAIssistant data from Hostinger database on startup"

function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "This script requires Administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

if ($Remove) {
    Write-Host "Removing scheduled task: $TaskName" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Task removed successfully." -ForegroundColor Green
    exit 0
}

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$TaskName' already exists. Updating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the scheduled task
Write-Host "Creating scheduled task: $TaskName" -ForegroundColor Cyan

# Action - run the batch file
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $PSScriptRoot

# Trigger - at user logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Principal - run as current user
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description $Description

Write-Host ""
Write-Host "Scheduled task created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Name: $TaskName"
Write-Host "  Trigger: At user logon"
Write-Host "  Script: $ScriptPath"
Write-Host ""

if ($RunNow) {
    Write-Host "Running task now..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Task started." -ForegroundColor Green
}

Write-Host "To manage this task:" -ForegroundColor Cyan
Write-Host "  - View: Open Task Scheduler and look for '$TaskName'"
Write-Host "  - Remove: Run this script with -Remove flag"
Write-Host "  - Test: Run this script with -RunNow flag"
