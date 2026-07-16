#!/usr/bin/env bash
set -euo pipefail
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/build/pyinstaller-cache}"
python -m PyInstaller --noconfirm --clean --windowed --name PetShelf --add-data "assets:assets" --collect-all PIL run_pet_shelf.py
echo "Built: dist/PetShelf.app"
