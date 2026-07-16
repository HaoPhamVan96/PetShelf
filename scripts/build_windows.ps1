$ErrorActionPreference = "Stop"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PWD "build\pyinstaller-cache"
python -m PyInstaller --noconfirm --clean --windowed --name PetShelf --collect-all PIL run_pet_shelf.py
Write-Host "Built: dist/PetShelf/PetShelf.exe"
