#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$ROOT/.venv/bin/pyinstaller" ]]; then
  echo "PyInstaller is not installed in .venv. Run:" >&2
  echo "  .venv/bin/python -m pip install pyinstaller" >&2
  exit 1
fi

cd "$ROOT/pyinstaller"
"$ROOT/.venv/bin/pyinstaller" \
  --clean \
  --noconfirm \
  --distpath "$ROOT/build/ipp-command" \
  --workpath "$ROOT/build/pyinstaller-ipp-work" \
  JadensIPPCommand.spec

echo "Built $ROOT/build/ipp-command/JadensIPPCommand/JadensIPPCommand"
