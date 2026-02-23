@echo off
setlocal

set PROJECT_DIR=%~dp0
set PYTHON_EXE=%PROJECT_DIR%my_env\Scripts\python.exe
set LOG_DIR=%PROJECT_DIR%logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo Starting backend in detached mode...
start "WaitressBackend" /min "%PYTHON_EXE%" "%PROJECT_DIR%run_waitress.py" 1>>"%LOG_DIR%\waitress_out.log" 2>>"%LOG_DIR%\waitress_err.log"

timeout /t 2 /nobreak >nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo Backend is running on port 8000. PID: %%P
  goto :done
)

echo Backend did not start. Check logs\waitress_err.log

:done
endlocal
