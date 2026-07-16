$ErrorActionPreference = "Stop"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PWD "build\pyinstaller-cache"
$Python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
& $Python -m PyInstaller --noconfirm --clean --windowed --name PetShelf --icon assets\petshelf.ico --add-data "assets;assets" --collect-all PIL run_pet_shelf.py
Write-Host "Built: dist/PetShelf/PetShelf.exe"
