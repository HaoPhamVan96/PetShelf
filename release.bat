@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\release.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo Release failed with exit code %EXIT_CODE%.
) else (
    echo Release completed.
)
pause
exit /b %EXIT_CODE%
