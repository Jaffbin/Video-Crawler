@echo off
setlocal
cd /d "%~dp0"
"runtime\python\python.exe" "portable_bootstrap.py" --with-playwright
pause
