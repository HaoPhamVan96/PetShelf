$ErrorActionPreference = "Stop"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PWD "build\pyinstaller-cache"
$DistApp = Join-Path $PWD "dist\PetShelf"
if (Test-Path $DistApp) {
    Remove-Item -LiteralPath $DistApp -Recurse -Force
}
$Python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
& $Python -m PyInstaller --noconfirm --clean --windowed --name PetShelf --paths . --icon assets\petshelf.ico --add-data "assets;assets" --collect-all PIL `
    --hidden-import pet_shelf.app `
    --hidden-import pet_shelf.ui `
    --hidden-import pet_shelf.models `
    --hidden-import pet_shelf.editor `
    --hidden-import pet_shelf.petdex `
    --hidden-import pet_shelf.updater `
    run_pet_shelf.py
Write-Host "Built: dist/PetShelf/PetShelf.exe"
