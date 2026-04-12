@echo off
REM ========================================
REM PoolAIssistant v6.1.1 - Deploy to Pi
REM ========================================

REM Accept target as command line argument or environment variable
REM Usage: deploy_to_pi.bat [user@host]
REM Or set environment: SET DEPLOY_TARGET=poolaissistant@10.0.30.80

IF "%1"=="" (
    IF "%DEPLOY_TARGET%"=="" (
        SET TARGET=poolaissistant@poolaissistant.local
    ) ELSE (
        SET TARGET=%DEPLOY_TARGET%
    )
) ELSE (
    SET TARGET=%1
)

REM Parse user@host
FOR /F "tokens=1,2 delims=@" %%A IN ("%TARGET%") DO (
    SET PI_USER=%%A
    SET PI_HOST=%%B
)

IF "%PI_HOST%"=="" (
    echo ERROR: Invalid target format. Use: user@host
    echo Example: deploy_to_pi.bat poolaissistant@poolaissistant.local
    pause
    exit /b 1
)

SET PI_TARGET=/home/%PI_USER%/PoolDash_v6

echo ========================================
echo PoolAIssistant Deployment Script
echo ========================================
echo.
echo Target: %PI_USER%@%PI_HOST%:%PI_TARGET%
echo.

REM Test connection first
echo [1/4] Testing connection to Pi...
ping -n 1 %PI_HOST% >nul
if errorlevel 1 (
    echo ERROR: Cannot reach Pi at %PI_HOST%
    echo Please check network connection and try again
    pause
    exit /b 1
)
echo OK - Pi is reachable
echo.

REM Check SSH connectivity
echo [2/4] Testing SSH connection...
ssh -o ConnectTimeout=5 %PI_USER%@%PI_HOST% "echo SSH OK" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Cannot SSH to %PI_USER%@%PI_HOST%
    echo Please check SSH keys or credentials
    pause
    exit /b 1
)
echo OK - SSH connection working
echo.

REM Transfer files
echo [3/4] Transferring files to Pi...
echo This may take a moment...
scp -r ^
    *.py ^
    requirements.txt ^
    README.md ^
    OPTIMIZATION_SUMMARY.md ^
    INSTALL.txt ^
    setup_pooldash.sh ^
    pooldash_app ^
    scripts ^
    %PI_USER%@%PI_HOST%:%PI_TARGET%/

if errorlevel 1 (
    echo ERROR: File transfer failed
    pause
    exit /b 1
)
echo OK - Files transferred
echo.

REM Install on Pi
echo [4/4] Installing on Pi...
ssh %PI_USER%@%PI_HOST% "cd %PI_TARGET% && bash setup_pooldash.sh"

if errorlevel 1 (
    echo WARNING: Installation script returned an error
    echo Check the output above for details
    echo.
    echo You may need to run manually:
    echo   ssh %PI_USER%@%PI_HOST%
    echo   cd %PI_TARGET%
    echo   sudo bash setup_pooldash.sh
    pause
    exit /b 1
)

echo.
echo ========================================
echo Deployment Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Check services are running:
echo    ssh %PI_USER%@%PI_HOST% "sudo systemctl status poolaissistant_logger"
echo    ssh %PI_USER%@%PI_HOST% "sudo systemctl status poolaissistant_ui"
echo.
echo 2. View logs:
echo    ssh %PI_USER%@%PI_HOST% "journalctl -u poolaissistant_logger -f"
echo.
echo 3. Access web UI:
echo    http://%PI_HOST%:8080
echo.
echo 4. Configure controllers in Settings if needed
echo.

pause
