#!/usr/bin/env python3
"""Launch the local IPP-to-BLE JADENS printer service."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def detect_app_root() -> Path:
    if "JADENS_APP_ROOT" in os.environ:
        return Path(os.environ["JADENS_APP_ROOT"]).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(1)


def default_ipp_attrs(root: Path) -> Path:
    packaged = root / "resources/JD-268BT-ipp-attrs.conf"
    if packaged.exists():
        return packaged
    return root / "src/JD-268BT-ipp-attrs.conf"


def main(argv: list[str]) -> int:
    root = detect_app_root()
    port = os.environ.get("JADENS_IPP_PORT", "8631")
    name = os.environ.get("JADENS_IPP_NAME", "Jadens 268BT BLE")
    ble_name = os.environ.get("JADENS_BLE_NAME", "JD-268BT")
    device_uri = os.environ.get("JADENS_DEVICE_URI", f"jadensble://{ble_name}")
    ppd = Path(os.environ.get("JADENS_PPD", "/Library/Printers/Jadens/PPDs/JD-268BT.ppd"))
    spool = root / "build/ipp-spool"
    ipp_attrs = Path(os.environ.get("JADENS_IPP_ATTRS", str(default_ipp_attrs(root))))
    packaged_command = root / "bin/JadensIPPCommand/JadensIPPCommand"
    source_command = root / "src/ipp_jadens_command.py"
    ble_app = Path(os.environ.get("JADENS_BLE_APP", str(root / "apps/BLEProbe.app")))

    if len(argv) > 1 and argv[1] in {"--help", "-h"}:
        print("Usage: JadensPrinterService")
        print()
        print("Environment overrides:")
        print(f"  JADENS_APP_ROOT={root}")
        print(f"  JADENS_IPP_PORT={port}")
        print(f"  JADENS_IPP_NAME={name!r}")
        print(f"  JADENS_BLE_NAME={ble_name}")
        print(f"  JADENS_DEVICE_URI={device_uri}")
        print(f"  JADENS_PPD={ppd}")
        print(f"  JADENS_IPP_ATTRS={ipp_attrs}")
        return 0

    if not ppd.exists():
        fail(f"Missing JADENS PPD: {ppd}\nInstall the JADENS macOS driver package first.")
    if not ipp_attrs.exists():
        fail(f"Missing IPP attributes file: {ipp_attrs}")

    if packaged_command.exists() and os.access(packaged_command, os.X_OK):
        command = packaged_command
    elif source_command.exists() and os.access(source_command, os.X_OK):
        command = source_command
    else:
        fail(f"Missing print command: {packaged_command}")

    if command == source_command and not (root / ".venv/bin/python").exists():
        fail(
            "Missing .venv. Run:\n"
            "  python3 -m venv .venv\n"
            "  .venv/bin/python -m pip install -r requirements.txt"
        )

    if not ble_app.exists():
        fallback = root / "build/python-probe/BLEProbe.app"
        if fallback.exists():
            ble_app = fallback
        else:
            fail(f"Missing BLEProbe.app: {ble_app}")

    spool.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    args = [
        "/usr/bin/ippeveprinter",
        "-v",
        "-p",
        port,
        "-d",
        str(spool),
        "-a",
        str(ipp_attrs),
    ]
    if os.environ.get("JADENS_IPP_KEEP_JOBS", "0") == "1":
        args.append("-k")
    args.extend(
        [
            "-l",
            "Local BLE",
            "-F",
            "application/pdf",
            "-D",
            device_uri,
            "-c",
            str(command),
            name,
        ]
    )

    print("Starting IPP printer app:", flush=True)
    print(f"  Name: {name}", flush=True)
    print(f"  URL:  ipp://localhost:{port}/ipp/print", flush=True)

    env = os.environ.copy()
    env["JADENS_APP_ROOT"] = str(root)
    env["JADENS_LOG_FILE"] = str(root / "logs/ipp-jadens-command.log")
    env["JADENS_BLE_APP"] = str(ble_app)
    os.execve(args[0], args, env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
