# Run this script as Administrator to create the scheduled task
$action = New-ScheduledTaskAction -Execute "$PSScriptRoot\run_sync.bat" -WorkingDirectory "$PSScriptRoot"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "bensa"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings
Register-ScheduledTask -TaskName "PoolAIssistant_Brain_Sync" -InputObject $task -Force
Write-Host "Scheduled task created successfully!"
