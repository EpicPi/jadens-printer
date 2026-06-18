#!/usr/bin/env bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/sbin:/sbin"

LABEL="com.kancharlawar.jadensprinter"
OLD_LABEL="com.local.jadens-printer-app"
QUEUE_NAME="${JADENS_QUEUE_NAME:-Jadens_268BT_BLE}"
IPP_PORT="${JADENS_IPP_PORT:-8631}"
DRIVER_PPD="/Library/Printers/Jadens/PPDs/JD-268BT.ppd"
DRIVER_FILTER="/Library/Printers/Jadens/Filter/rastertolabel"
DRIVER_URL="${JADENS_DRIVER_URL:-https://cdn.shopify.com/s/files/1/0574/8742/5675/files/Jadens-Printer-Driver_macos_3.3.6.506_90b9ffc8-6ec4-488a-977b-1e740f8d9023.pkg?v=1779690705}"
DRIVER_SHA256="${JADENS_DRIVER_SHA256:-95cdc645a45dc497b2b237f5aa6f4b651ef392197a2198ad27091f73ad7f49fa}"

SYSTEM_PAYLOAD_ROOT="/Library/Application Support/JadensPrinterApp/package-payload"
APP_PAYLOAD="$SYSTEM_PAYLOAD_ROOT/app"
INSTALL_LOG="/tmp/jadens-printer-install.log"

exec > >(tee -a "$INSTALL_LOG") 2>&1

log() {
  echo "JADENS Printer App: $*"
}

console_user() {
  local user
  user="$(stat -f %Su /dev/console)"
  if [[ -z "$user" || "$user" == "root" || "$user" == "loginwindow" ]]; then
    echo "Could not determine the logged-in user." >&2
    exit 1
  fi
  echo "$user"
}

user_home() {
  local user="$1"
  local home
  home="$(dscl . -read "/Users/$user" NFSHomeDirectory 2>/dev/null | awk -F': ' '/NFSHomeDirectory/ {print $2}')"
  if [[ -z "$home" || ! -d "$home" ]]; then
    echo "Could not determine home directory for $user." >&2
    exit 1
  fi
  echo "$home"
}

driver_installed() {
  if [[ -f "$DRIVER_PPD" && -x "$DRIVER_FILTER" ]]; then
    return 0
  fi
  return 1
}

verify_driver_installed() {
  if driver_installed; then
    log "JADENS driver is installed."
    return
  fi

  echo "The JADENS driver files were not found." >&2
  echo "Missing: $DRIVER_PPD or $DRIVER_FILTER" >&2
  echo "Install log: $INSTALL_LOG" >&2
  exit 1
}

install_driver_if_needed() {
  local tmp_dir driver_pkg actual_sha

  if driver_installed; then
    log "JADENS driver is already installed."
    return
  fi

  if [[ "${JADENS_SKIP_DRIVER_DOWNLOAD:-0}" == "1" ]]; then
    verify_driver_installed
  fi

  tmp_dir="$(mktemp -d)"
  driver_pkg="$tmp_dir/jadens-driver.pkg"

  log "Downloading JADENS macOS driver package."
  if ! curl -fL --retry 3 --connect-timeout 20 -o "$driver_pkg" "$DRIVER_URL"; then
    rm -rf "$tmp_dir"
    echo "Could not download the JADENS driver package." >&2
    echo "URL: $DRIVER_URL" >&2
    echo "Install log: $INSTALL_LOG" >&2
    exit 1
  fi

  actual_sha="$(shasum -a 256 "$driver_pkg" | awk '{print $1}')"
  if [[ "$actual_sha" != "$DRIVER_SHA256" ]]; then
    rm -rf "$tmp_dir"
    echo "Downloaded JADENS driver checksum did not match." >&2
    echo "Expected: $DRIVER_SHA256" >&2
    echo "Actual:   $actual_sha" >&2
    echo "Install log: $INSTALL_LOG" >&2
    exit 1
  fi

  log "Installing JADENS macOS driver package."
  if ! installer -pkg "$driver_pkg" -target /; then
    rm -rf "$tmp_dir"
    echo "The JADENS driver package installer failed." >&2
    echo "Install log: $INSTALL_LOG" >&2
    exit 1
  fi

  rm -rf "$tmp_dir"
  verify_driver_installed
}

stop_stale_printer_processes() {
  local uid="$1"
  local pid

  for pattern in \
    'ippeveprinter.*Jadens 268BT BLE' \
    'ippeveprinter.*jadensble://JD-268BT'; do
    while IFS= read -r pid; do
      if [[ -n "$pid" && "$pid" != "$$" ]]; then
        log "Stopping stale printer app process $pid"
        kill "$pid" 2>/dev/null || true
      fi
    done < <(pgrep -U "$uid" -f "$pattern" 2>/dev/null || true)
  done

  for _ in $(seq 1 5); do
    if ! nc -z localhost "$IPP_PORT" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
}

cleanup_previous_install() {
  local home="$1"
  local install_root="$2"
  local uid="$3"
  local launch_agent="$home/Library/LaunchAgents/$LABEL.plist"
  local old_launch_agent="$home/Library/LaunchAgents/$OLD_LABEL.plist"

  log "Cleaning up any previous partial install."
  launchctl bootout "gui/$uid" "$launch_agent" >/dev/null 2>&1 || true
  launchctl bootout "gui/$uid" "$old_launch_agent" >/dev/null 2>&1 || true
  rm -f "$launch_agent"
  rm -f "$old_launch_agent"
  lpadmin -x "$QUEUE_NAME" >/dev/null 2>&1 || true
  stop_stale_printer_processes "$uid"
  rm -rf "$install_root"
}

install_app_files() {
  local install_root="$1"
  local uid="$2"
  local gid="$3"

  if [[ ! -d "$APP_PAYLOAD" ]]; then
    echo "Missing package payload: $APP_PAYLOAD" >&2
    exit 1
  fi

  log "Installing app files to $install_root"
  mkdir -p "$install_root"
  rsync -a --delete "$APP_PAYLOAD/" "$install_root/"
  mkdir -p "$install_root/logs" "$install_root/build"
  chown -R "$uid:$gid" "$install_root"
  xattr -dr com.apple.quarantine "$install_root" 2>/dev/null || true
  rm -rf "$SYSTEM_PAYLOAD_ROOT"
}

install_launch_agent() {
  local user_home="$1"
  local install_root="$2"
  local uid="$3"
  local gid="$4"
  local launch_agent="$user_home/Library/LaunchAgents/$LABEL.plist"

  mkdir -p "$user_home/Library/LaunchAgents"
  cat > "$launch_agent" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$install_root/bin/JadensPrinterService/JadensPrinterService</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>JADENS_APP_ROOT</key>
    <string>$install_root</string>
    <key>JADENS_IPP_PORT</key>
    <string>$IPP_PORT</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$install_root/logs/printer-app.out.log</string>
  <key>StandardErrorPath</key>
  <string>$install_root/logs/printer-app.err.log</string>
</dict>
</plist>
PLIST

  chown "$uid:$gid" "$launch_agent"
  chmod 644 "$launch_agent"

  launchctl bootout "gui/$uid" "$launch_agent" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$uid" "$launch_agent"
  launchctl enable "gui/$uid/$LABEL" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/$uid/$LABEL"
}

wait_for_ipp() {
  log "Waiting for local IPP printer app on port $IPP_PORT"
  for _ in $(seq 1 20); do
    if nc -z localhost "$IPP_PORT" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "The printer app did not start listening on port $IPP_PORT." >&2
  exit 1
}

install_queue() {
  log "Creating CUPS queue $QUEUE_NAME"
  lpadmin -x "$QUEUE_NAME" >/dev/null 2>&1 || true
  lpadmin -p "$QUEUE_NAME" -E -v "ipp://localhost:$IPP_PORT/ipp/print" -m everywhere
  lpstat -p "$QUEUE_NAME"
}

prime_bluetooth_permission() {
  local user="$1"
  local uid="$2"
  local install_root="$3"

  log "Priming Bluetooth permission for BLE helper."
  launchctl asuser "$uid" sudo -u "$user" \
    "$install_root/scripts/run_ble_probe_app.sh" --timeout 4 scan --name JD-268BT || true
}

main() {
  local user home uid gid install_root

  user="$(console_user)"
  home="$(user_home "$user")"
  uid="$(id -u "$user")"
  gid="$(id -g "$user")"
  install_root="$home/Library/Application Support/JadensPrinterApp"

  log "Starting postinstall for $user"
  cleanup_previous_install "$home" "$install_root" "$uid"
  install_driver_if_needed
  install_app_files "$install_root" "$uid" "$gid"
  install_launch_agent "$home" "$install_root" "$uid" "$gid"
  wait_for_ipp
  install_queue
  prime_bluetooth_permission "$user" "$uid" "$install_root"

  log "Installed $QUEUE_NAME for $user."
}

main "$@"
