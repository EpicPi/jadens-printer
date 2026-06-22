#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import PyInstaller' >/dev/null 2>&1; then
  echo "PyInstaller is not installed in .venv. Run:" >&2
  echo "  .venv/bin/python -m pip install pyinstaller" >&2
  exit 1
fi

cd "$ROOT/pyinstaller"
"$PYTHON" -m PyInstaller \
  --clean \
  --noconfirm \
  --distpath "$ROOT/build/service" \
  --workpath "$ROOT/build/pyinstaller-service-work" \
  JadensPrinterService.spec

echo "Built $ROOT/build/service/JadensPrinterService/JadensPrinterService"
