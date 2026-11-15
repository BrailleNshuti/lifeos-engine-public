@echo off
setlocal
title LifeOS Study Atelier
set "LIFEOS_HOME=C:\Users\you\lifeos"
set "ENGINE_HOME=C:\Users\you\lifeos-engine"
set "PYTHON_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"

if not defined PYTHON_EXE (
  echo Python was not found. Install Python 3.10 or newer, then try again.
  pause
  exit /b 1
)

cd /d "%ENGINE_HOME%"
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8765/#learning'"
echo Starting LifeOS Study Atelier...
echo Keep this window open. Press Ctrl+C to stop the Cockpit.
"%PYTHON_EXE%" -m lifeos.cli --home "%LIFEOS_HOME%" cockpit --serve

if errorlevel 1 pause
endlocal
