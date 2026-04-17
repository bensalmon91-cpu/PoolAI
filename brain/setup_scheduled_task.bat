@echo off
schtasks /create /tn "PoolAI_Brain_Backup" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File %~dp0backup_to_icloud.ps1" /sc onlogon /ru %USERNAME% /rl highest /f
echo.
echo Task created. You can verify in Task Scheduler.
pause
