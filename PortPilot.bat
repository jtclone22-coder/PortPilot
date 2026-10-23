@echo off
rem PortPilot launcher. No arguments: open the window. With arguments: run the command line.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  where pyw >nul 2>nul && (start "" pyw -3 -m portpilot & exit /b 0)
  where pythonw >nul 2>nul && (start "" pythonw -m portpilot & exit /b 0)
) else (
  where py >nul 2>nul && (py -3 -m portpilot %* & exit /b)
  where python >nul 2>nul && (python -m portpilot %* & exit /b)
)
echo PortPilot needs Python 3.9 or newer: https://www.python.org/downloads/windows/
pause
