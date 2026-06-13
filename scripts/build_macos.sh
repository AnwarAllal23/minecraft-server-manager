#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller"

.venv/bin/python -m PyInstaller --noconfirm --clean GestionServeursMinecraft.spec

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "dist/Gestion Serveurs Minecraft.app"
fi

echo "Application créée: $ROOT_DIR/dist/Gestion Serveurs Minecraft.app"
