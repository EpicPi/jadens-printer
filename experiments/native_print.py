#!/usr/bin/env python3
"""
Check and use native macOS printing if the JADENS printer is installed as a
CUPS destination.

Examples:
  python experiments/native_print.py list
  python experiments/native_print.py print --printer JD_268BT label.pdf
  python experiments/native_print.py open-settings
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def list_destinations() -> int:
    lpstat_v = run_command(["lpstat", "-v"])
    lpstat_p = run_command(["lpstat", "-p"])

    if lpstat_v.returncode != 0 and "No destinations added" in lpstat_v.stderr:
        print("No CUPS printer destinations are installed.")
    else:
        print("CUPS devices:")
        print((lpstat_v.stdout or lpstat_v.stderr).strip() or "(none)")

    if lpstat_p.returncode == 0:
        print("\nCUPS printers:")
        print(lpstat_p.stdout.strip() or "(none)")

    profiler = run_command(["system_profiler", "SPBluetoothDataType"])
    matches = [
        line
        for line in profiler.stdout.splitlines()
        if any(token in line.lower() for token in ["jadens", "jaden", "jd-268", "thermal", "printer"])
    ]
    if matches:
        print("\nBluetooth entries that look relevant:")
        for line in matches:
            print(line)
    else:
        print("\nNo obvious JADENS Bluetooth entry found in system_profiler output.")

    return 0


def print_file(printer: str, path: Path) -> int:
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    command = ["lp", "-d", printer, str(path)]
    print("Running:", " ".join(command))
    result = run_command(command)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def open_settings() -> int:
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.Print-Scan-Settings.extension"],
        check=False,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list CUPS destinations and Bluetooth hints")
    subparsers.add_parser("open-settings", help="open Printers & Scanners settings")

    print_parser = subparsers.add_parser("print", help="print through an installed CUPS destination")
    print_parser.add_argument("--printer", required=True, help="CUPS destination name")
    print_parser.add_argument("file", type=Path)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list":
        return list_destinations()
    if args.command == "print":
        return print_file(args.printer, args.file)
    if args.command == "open-settings":
        return open_settings()
    raise ValueError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
