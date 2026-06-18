#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${JADENS_BLE_APP:-}" ]]; then
  APP="$JADENS_BLE_APP"
elif [[ -d "$ROOT/apps/BLEProbe.app" ]]; then
  APP="$ROOT/apps/BLEProbe.app"
else
  APP="$ROOT/build/python-probe/BLEProbe.app"
fi
OUT="$ROOT/build/bleprobe.out"
ERR="$ROOT/build/bleprobe.err"
mkdir -p "$(dirname "$OUT")"

if [[ ! -d "$APP" ]]; then
  echo "Missing $APP" >&2
  echo "Build it first with:" >&2
  echo "  ./packaging/build_ble_probe_app.sh" >&2
  exit 1
fi

rm -f "$OUT" "$ERR"
open -W -n -o "$OUT" --stderr "$ERR" "$APP" --args "$@"

if [[ -s "$OUT" ]]; then
  cat "$OUT"
fi

if [[ -s "$ERR" ]]; then
  cat "$ERR" >&2
fi
