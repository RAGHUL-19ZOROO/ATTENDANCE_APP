@echo off
setlocal

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo Stopping backend PID %%P...
  taskkill /PID %%P /F >nul 2>&1
)

echo Done.
endlocal
