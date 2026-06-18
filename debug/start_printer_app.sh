#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPOOL="$ROOT/build/ipp-spool"
MEDIA_PPD="${JADENS_IPP_MEDIA_PPD:-$ROOT/src/JD-268BT-media.ppd}"
PORT="${JADENS_IPP_PORT:-8631}"
NAME="${JADENS_IPP_NAME:-Jadens 268BT BLE}"
BLE_NAME="${JADENS_BLE_NAME:-JD-268BT}"
DEVICE_URI="${JADENS_DEVICE_URI:-jadensble://$BLE_NAME}"
PPD="${JADENS_PPD:-/Library/Printers/Jadens/PPDs/JD-268BT.ppd}"
if [[ -n "${JADENS_BLE_APP:-}" ]]; then
  BLE_APP="$JADENS_BLE_APP"
elif [[ -d "$ROOT/apps/BLEProbe.app" ]]; then
  BLE_APP="$ROOT/apps/BLEProbe.app"
else
  BLE_APP="$ROOT/build/python-probe/BLEProbe.app"
fi
if [[ -x "$ROOT/bin/JadensIPPCommand/JadensIPPCommand" ]]; then
  COMMAND="$ROOT/bin/JadensIPPCommand/JadensIPPCommand"
else
  COMMAND="$ROOT/src/ipp_jadens_command.py"
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: $0"
  echo
  echo "Environment overrides:"
  echo "  JADENS_IPP_PORT=$PORT"
  echo "  JADENS_IPP_NAME=\"$NAME\""
  echo "  JADENS_PPD=$PPD"
  echo "  JADENS_IPP_MEDIA_PPD=$MEDIA_PPD"
  echo "  JADENS_BLE_NAME=$BLE_NAME"
  echo "  JADENS_DEVICE_URI=$DEVICE_URI"
  echo "  JADENS_BLE_CHAR=0000fff2-0000-1000-8000-00805f9b34fb"
  exit 0
fi

if [[ ! -f "$PPD" ]]; then
  echo "Missing JADENS PPD: $PPD" >&2
  echo "Install the JADENS macOS driver package first." >&2
  exit 1
fi

if [[ ! -x "$COMMAND" ]]; then
  echo "Missing print command: $COMMAND" >&2
  exit 1
fi

if [[ "$COMMAND" == "$ROOT/src/ipp_jadens_command.py" && ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing .venv. Run:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -d "$BLE_APP" ]]; then
  "$ROOT/packaging/build_ble_probe_app.sh"
fi

if [[ ! -f "$MEDIA_PPD" ]]; then
  echo "Missing IPP media PPD: $MEDIA_PPD" >&2
  exit 1
fi

mkdir -p "$SPOOL"

KEEP_ARGS=()
if [[ "${JADENS_IPP_KEEP_JOBS:-0}" == "1" ]]; then
  KEEP_ARGS=(-k)
fi

echo "Starting IPP printer app:"
echo "  Name: $NAME"
echo "  URL:  ipp://localhost:$PORT/ipp/print"
echo "  Add it in System Settings -> Printers & Scanners, or run:"
echo "  lpadmin -p Jadens_268BT_BLE -E -v ipp://localhost:$PORT/ipp/print -m everywhere"

exec env \
  "JADENS_APP_ROOT=$ROOT" \
  "JADENS_LOG_FILE=$ROOT/logs/ipp-jadens-command.log" \
  "JADENS_BLE_APP=$BLE_APP" \
  /usr/bin/ippeveprinter \
  -v \
  -p "$PORT" \
  -d "$SPOOL" \
  -P "$MEDIA_PPD" \
  ${KEEP_ARGS[@]+"${KEEP_ARGS[@]}"} \
  -l "Local BLE" \
  -F "application/pdf" \
  -D "$DEVICE_URI" \
  -c "$COMMAND" \
  "$NAME"
