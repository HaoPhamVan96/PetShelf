@echo off
setlocal

cd /d "%~dp0"

echo Building PetShelf.exe...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1"
set "BUILD_EXIT=%ERRORLEVEL%"

echo.
if "%BUILD_EXIT%"=="0" (
    echo Done: %~dp0dist\PetShelf\PetShelf.exe
) else (
    echo Build failed with exit code %BUILD_EXIT%.
)

echo.
pause
exit /b %BUILD_EXIT%
