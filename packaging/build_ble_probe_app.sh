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
  --distpath "$ROOT/build/python-probe" \
  --workpath "$ROOT/build/pyinstaller-work" \
  BLEProbe.spec

APP="$ROOT/build/python-probe/BLEProbe.app"
CLEAN_APP="$ROOT/build/python-probe/BLEProbe.clean.app"
rm -rf "$CLEAN_APP"
ditto --norsrc --noextattr --noqtn "$APP" "$CLEAN_APP"
rm -rf "$APP"
mv "$CLEAN_APP" "$APP"
codesign -s - --force --deep "$APP"
xattr -d com.apple.FinderInfo "$APP" 2>/dev/null || true
xattr -d 'com.apple.fileprovider.fpfs#P' "$APP" 2>/dev/null || true

echo "Built $ROOT/build/python-probe/BLEProbe.app"
