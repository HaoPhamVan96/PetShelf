@echo off
setlocal

cd /d "%~dp0"

echo PetShelf macOS build
echo.
echo A native .app must be built on macOS. PyInstaller does not cross-compile
echo macOS applications from Windows.
echo.
echo On a Mac, double-click build-macos.command or run:
echo     bash scripts/build_macos.sh
echo.
pause
exit /b 1
