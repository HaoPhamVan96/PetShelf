#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON=".venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing build dependencies..."
"$PYTHON" -m pip install -r requirements-dev.txt

echo "Building PetShelf.app..."
bash scripts/build_macos.sh

echo
echo "Done: $PROJECT_DIR/dist/PetShelf.app"
read -r -p "Press Enter to close..."
