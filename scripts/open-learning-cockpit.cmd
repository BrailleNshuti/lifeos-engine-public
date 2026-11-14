@echo off
setlocal
title LifeOS Learning Studio
set "LIFEOS_HOME=C:\Users\you\lifeos"
set "ENGINE_HOME=C:\Users\you\lifeos-engine"
set "PYTHON_EXE=C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Python was not found at:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

cd /d "%ENGINE_HOME%"
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8765/'"
echo Starting LifeOS Learning Studio...
echo Keep this window open. Press Ctrl+C to stop the Cockpit.
"%PYTHON_EXE%" -m lifeos.cli --home "%LIFEOS_HOME%" cockpit --serve

if errorlevel 1 pause
endlocal
