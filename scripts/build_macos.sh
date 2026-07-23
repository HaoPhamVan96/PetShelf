#!/usr/bin/env bash
set -euo pipefail
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/build/pyinstaller-cache}"
PYTHON="${PYTHON:-python}"
if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
fi
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed --name PetShelf --paths . \
    --add-data "assets:assets" --collect-all PIL \
    --hidden-import pet_shelf.app \
    --hidden-import pet_shelf.ui \
    --hidden-import pet_shelf.models \
    --hidden-import pet_shelf.editor \
    --hidden-import pet_shelf.petdex \
    --hidden-import pet_shelf.updater \
    run_pet_shelf.py
echo "Built: dist/PetShelf.app"
