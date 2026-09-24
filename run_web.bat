@echo off
REM GenAgent One-Click Multi-Device Web Server Runner for Windows
cd /d "%~dp0"
echo ========================================================
echo     Starting GenAgent Multi-Device Web Server...
echo ========================================================
python web_server.py --port 8080
if %ERRORLEVEL% NEQ 0 (
    python3 web_server.py --port 8080
)
pause
