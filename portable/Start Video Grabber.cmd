@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo Portable Python is missing. Extract the complete ZIP and try again.
  pause
  exit /b 1
)
"runtime\python\python.exe" "portable_launcher.py" %*
if errorlevel 1 pause
