#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${JADENS_VERSION:-0.1.2}"
DIST_ROOT="$ROOT/dist"
RELEASE="$DIST_ROOT/JadensPrinterApp-$VERSION"
APP_PAYLOAD="$RELEASE/app"

export COPYFILE_DISABLE=1

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing .venv. Run:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt" >/dev/null
"$ROOT/.venv/bin/python" -m pip install pyinstaller >/dev/null

"$ROOT/packaging/build_ble_probe_app.sh"
"$ROOT/packaging/build_ipp_command.sh"
"$ROOT/packaging/build_service.sh"

rm -rf "$RELEASE"
mkdir -p "$APP_PAYLOAD/apps" "$APP_PAYLOAD/bin" "$APP_PAYLOAD/scripts" "$APP_PAYLOAD/logs"

ditto --norsrc --noextattr --noqtn "$ROOT/build/python-probe/BLEProbe.app" "$APP_PAYLOAD/apps/BLEProbe.app"
ditto --norsrc --noextattr --noqtn "$ROOT/build/ipp-command/JadensIPPCommand" "$APP_PAYLOAD/bin/JadensIPPCommand"
ditto --norsrc --noextattr --noqtn "$ROOT/build/service/JadensPrinterService" "$APP_PAYLOAD/bin/JadensPrinterService"
cp "$ROOT/src/run_ble_probe_app.sh" "$APP_PAYLOAD/scripts/run_ble_probe_app.sh"
chmod +x "$APP_PAYLOAD/scripts/run_ble_probe_app.sh"
codesign -s - --force --deep "$APP_PAYLOAD/apps/BLEProbe.app"
xattr -d com.apple.FinderInfo "$APP_PAYLOAD/apps/BLEProbe.app" 2>/dev/null || true
xattr -d 'com.apple.fileprovider.fpfs#P' "$APP_PAYLOAD/apps/BLEProbe.app" 2>/dev/null || true

"$ROOT/packaging/build_macos_pkg.sh"

echo "Built release:"
echo "  $RELEASE"
echo "  $DIST_ROOT/JadensPrinterApp-$VERSION.pkg"
