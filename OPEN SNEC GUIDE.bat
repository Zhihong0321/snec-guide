@echo off
title SNEC 2026 Guide
cd /d "%~dp0"

where py >nul 2>&1 && (set PY=py -3& goto run)
where python >nul 2>&1 && (set PY=python& goto run)

echo.
echo  Python is not installed or not on PATH.
echo  Install from https://www.python.org/downloads/
echo  Check "Add python.exe to PATH" during install.
echo.
pause
exit /b 1

:run
echo.
echo  SNEC 2026 Guide — starting...
echo  Your browser will open automatically.
echo  DO NOT close this window while using the app.
echo.
%PY% run_web.py
echo.
echo  Server stopped.
pause
