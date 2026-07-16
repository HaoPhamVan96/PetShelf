$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 from python.org and enable Add Python to PATH."
}

$Venv = Join-Path $Root "work\windows-build-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -3.12 -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-dev.txt
& $Python -m PyInstaller --noconfirm --clean --windowed --name PetShelf --icon assets\petshelf.ico --add-data "assets;assets" --collect-all PIL run_pet_shelf.py

$Outputs = Join-Path $Root "outputs"
New-Item -ItemType Directory -Force -Path $Outputs | Out-Null
$ZipPath = Join-Path $Outputs "PetShelf-Windows-x64.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $Root "dist\PetShelf") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Built EXE: dist\PetShelf\PetShelf.exe"
Write-Host "Packaged: outputs\PetShelf-Windows-x64.zip"
