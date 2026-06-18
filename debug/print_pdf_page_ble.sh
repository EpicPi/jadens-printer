#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 PDF [PAGE]" >&2
  exit 2
fi

PDF="$1"
PAGE="${2:-1}"
OUT="$ROOT/build/jadens-page-${PAGE}.raw"
BLE_NAME="${JADENS_BLE_NAME:-JD-268BT}"
BLE_CHAR="${JADENS_BLE_CHAR:-0000fff2-0000-1000-8000-00805f9b34fb}"
BLE_CHUNK_SIZE="${JADENS_BLE_CHUNK_SIZE:-180}"
BLE_DELAY="${JADENS_BLE_DELAY:-0.005}"
BLE_LISTEN="${JADENS_BLE_LISTEN:-3}"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing .venv. Run:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

"$ROOT/.venv/bin/python" "$ROOT/src/prepare_jadens_raw.py" \
  "$PDF" \
  --page "$PAGE" \
  --output "$OUT"

if [[ ! -d "$ROOT/build/python-probe/BLEProbe.app" ]]; then
  "$ROOT/packaging/build_ble_probe_app.sh"
fi

"$ROOT/src/run_ble_probe_app.sh" \
  --timeout 10 \
  write-file \
  --name "$BLE_NAME" \
  --char "$BLE_CHAR" \
  --chunk-size "$BLE_CHUNK_SIZE" \
  --delay "$BLE_DELAY" \
  --listen "$BLE_LISTEN" \
  "$OUT"
