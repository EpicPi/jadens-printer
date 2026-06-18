#!/usr/bin/env python3
"""
Quick BLE probe for JADENS thermal printers.

Examples:
  python src/ble_probe.py scan
  python src/ble_probe.py gatt --name JD-268BT
  python src/ble_probe.py test --name JD-268BT --lang tspl
  python src/ble_probe.py write-hex --name JD-268BT "1B 40 0A"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: bleak\n"
        "Install it with:\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/python -m pip install -r requirements.txt\n"
        "  .venv/bin/python src/ble_probe.py scan"
    ) from exc


@dataclass(frozen=True)
class ProbeCommand:
    label: str
    data: bytes


def escpos_test() -> ProbeCommand:
    return ProbeCommand(
        "ESC/POS text test",
        b"\x1b@"
        b"JADENS BLE TEST\n"
        b"If this printed, ESC/POS over BLE works.\n\n"
        b"\x1bd\x03",
    )


def tspl_test() -> ProbeCommand:
    return ProbeCommand(
        "TSPL text test",
        (
            'SIZE 100 mm,150 mm\r\n'
            'GAP 2 mm,0 mm\r\n'
            'DENSITY 8\r\n'
            'SPEED 4\r\n'
            'DIRECTION 1\r\n'
            'CLS\r\n'
            'TEXT 40,40,"3",0,1,1,"JADENS BLE TEST"\r\n'
            'TEXT 40,95,"2",0,1,1,"If this printed, TSPL works."\r\n'
            'PRINT 1\r\n'
        ).encode("ascii"),
    )


def parse_hex(text: str) -> bytes:
    normalized = (
        text.replace("0x", "")
        .replace("0X", "")
        .replace(",", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )
    tokens = [token for token in normalized.split(" ") if token]
    if not tokens:
        raise ValueError("expected at least one hex byte")

    output = bytearray()
    for token in tokens:
        if len(token) > 2:
            raise ValueError(f"invalid hex byte {token!r}")
        output.append(int(token, 16))
    return bytes(output)


def hex_preview(data: bytes, limit: int = 96) -> str:
    prefix = " ".join(f"{byte:02X}" for byte in data[:limit])
    if len(data) > limit:
        return f"{prefix} ... (+{len(data) - limit} bytes)"
    return prefix


def char_is_writable(char: BleakGATTCharacteristic) -> bool:
    return "write-without-response" in char.properties or "write" in char.properties


def char_score(char: BleakGATTCharacteristic) -> int:
    score = 0
    uuid = char.uuid.upper()
    properties = set(char.properties)
    if "write-without-response" in properties:
        score += 100
    if "write" in properties:
        score += 50
    if uuid.endswith("FFE1") or uuid.endswith("FF01") or uuid.endswith("FFF1"):
        score += 25
    if "FFE" in uuid or "FF0" in uuid:
        score += 10
    return score


def pick_write_characteristic(
    chars: Iterable[BleakGATTCharacteristic],
    requested_uuid: str | None,
) -> BleakGATTCharacteristic:
    writable = [char for char in chars if char_is_writable(char)]
    if requested_uuid:
        requested = requested_uuid.lower()
        for char in writable:
            if char.uuid.lower() == requested or char.uuid.lower().endswith(requested):
                return char
        raise ValueError(f"no writable characteristic matched {requested_uuid!r}")

    if not writable:
        raise ValueError("no writable characteristics discovered")
    return sorted(writable, key=char_score, reverse=True)[0]


async def discover_services(client: BleakClient):
    services = getattr(client, "services", None)
    if services:
        return services
    get_services = getattr(client, "get_services", None)
    if get_services is None:
        raise RuntimeError("connected client did not expose services")
    return await get_services()


async def find_device(name: str | None, address: str | None, timeout: float):
    if address:
        device = await BleakScanner.find_device_by_address(address, timeout=timeout)
        if device is None:
            raise RuntimeError(f"no BLE device found at address {address!r}")
        return device

    needle = (name or "JD-268BT").lower()

    def matches(device, advertisement_data):
        device_name = (device.name or advertisement_data.local_name or "").lower()
        return needle in device_name

    device = await BleakScanner.find_device_by_filter(matches, timeout=timeout)
    if device is None:
        raise RuntimeError(f"no BLE device found matching name substring {needle!r}")
    return device


async def scan(args: argparse.Namespace) -> None:
    print(f"Scanning for {args.timeout:.1f}s...")
    discovered = await BleakScanner.discover(timeout=args.timeout, return_adv=True)

    rows = []
    for device, adv in discovered.values():
        name = device.name or adv.local_name or ""
        if args.name and args.name.lower() not in name.lower():
            continue
        rows.append((adv.rssi, name or "(unnamed)", device.address, adv.service_uuids))

    rows.sort(reverse=True)
    for rssi, name, address, service_uuids in rows:
        services = ",".join(service_uuids) if service_uuids else "-"
        print(f"{rssi:>4}  {name:<32}  {address}  services={services}")


async def print_gatt(args: argparse.Namespace) -> None:
    device = await find_device(args.name, args.address, args.timeout)
    print(f"Connecting to {device.name or '(unnamed)'} {device.address}...")
    async with BleakClient(device) as client:
        services = await discover_services(client)
        for service in services:
            print(f"\nservice {service.uuid}  {service.description}")
            for char in service.characteristics:
                properties = ",".join(char.properties)
                marker = " writable" if char_is_writable(char) else ""
                print(f"  char {char.uuid}  props={properties}{marker}")
                for descriptor in char.descriptors:
                    print(f"    desc {descriptor.uuid}  handle={descriptor.handle}")


async def send_commands(args: argparse.Namespace, commands: list[ProbeCommand]) -> None:
    if not commands:
        raise ValueError("expected at least one command")

    device = await find_device(args.name, args.address, args.timeout)
    print(f"Connecting to {device.name or '(unnamed)'} {device.address}...")
    async with BleakClient(device) as client:
        services = await discover_services(client)
        chars = [char for service in services for char in service.characteristics]

        notify_chars = [
            char
            for char in chars
            if "notify" in char.properties or "indicate" in char.properties
        ]
        for char in notify_chars:
            try:
                await client.start_notify(
                    char,
                    lambda sender, data: print(
                        f"notify {sender}: {hex_preview(bytes(data), 64)}"
                    ),
                )
                print(f"subscribed {char.uuid}")
            except Exception as exc:  # noqa: BLE transports vary by device.
                print(f"could not subscribe {char.uuid}: {exc}")

        char = pick_write_characteristic(chars, args.char)
        response = "write-without-response" not in char.properties and "write" in char.properties
        chunk_size = args.chunk_size or getattr(char, "max_write_without_response_size", 0) or 180
        chunk_size = max(20, min(chunk_size, 512))

        print(f"write characteristic: {char.uuid}")
        print(f"properties: {','.join(char.properties)}")
        print(f"write response: {response}")

        total_bytes = sum(len(command.data) for command in commands)
        print(f"payloads: {len(commands)}, total bytes={total_bytes}")

        for index, command in enumerate(commands, start=1):
            print(f"payload {index}/{len(commands)}: {command.label}, {len(command.data)} bytes")
            print(f"preview: {hex_preview(command.data)}")
            for offset in range(0, len(command.data), chunk_size):
                chunk = command.data[offset : offset + chunk_size]
                await client.write_gatt_char(char, chunk, response=response)
                if args.delay:
                    await asyncio.sleep(args.delay)
            file_delay = getattr(args, "file_delay", 0.0)
            if index != len(commands) and file_delay:
                await asyncio.sleep(file_delay)

        if args.listen:
            print(f"listening for notifications for {args.listen:.1f}s...")
            await asyncio.sleep(args.listen)


async def send_command(args: argparse.Namespace, command: ProbeCommand) -> None:
    await send_commands(args, [command])


async def run(args: argparse.Namespace) -> None:
    if args.command == "scan":
        await scan(args)
    elif args.command == "gatt":
        await print_gatt(args)
    elif args.command == "test":
        command = tspl_test() if args.lang == "tspl" else escpos_test()
        await send_command(args, command)
    elif args.command == "write-hex":
        await send_command(args, ProbeCommand("raw hex", parse_hex(args.hex_bytes)))
    elif args.command == "write-file":
        data = args.file.read_bytes()
        if args.strip_leading_nuls:
            data = data.lstrip(b"\x00")
        await send_command(args, ProbeCommand(f"raw file {args.file.name}", data))
    elif args.command == "write-files":
        commands = []
        for file in args.files:
            data = file.read_bytes()
            if args.strip_leading_nuls:
                data = data.lstrip(b"\x00")
            commands.append(ProbeCommand(f"raw file {file.name}", data))
        await send_commands(args, commands)
    else:
        raise ValueError(f"unknown command {args.command!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=8.0)

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan for BLE devices")
    scan_parser.add_argument("--name", help="optional name substring filter")

    def add_connect_args(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--name", default="JD-268BT", help="BLE name substring")
        command_parser.add_argument("--address", help="BLE address/UUID from scan output")

    gatt_parser = subparsers.add_parser("gatt", help="connect and dump services")
    add_connect_args(gatt_parser)

    test_parser = subparsers.add_parser("test", help="send a small printer-language test")
    add_connect_args(test_parser)
    test_parser.add_argument("--lang", choices=["tspl", "escpos"], default="tspl")
    test_parser.add_argument("--char", help="write characteristic UUID or suffix")
    test_parser.add_argument("--chunk-size", type=int, help="override BLE write chunk size")
    test_parser.add_argument("--delay", type=float, default=0.02, help="delay between chunks")
    test_parser.add_argument("--listen", type=float, default=1.0, help="notification listen time after writing")

    hex_parser = subparsers.add_parser("write-hex", help="send raw hex bytes")
    add_connect_args(hex_parser)
    hex_parser.add_argument("hex_bytes")
    hex_parser.add_argument("--char", help="write characteristic UUID or suffix")
    hex_parser.add_argument("--chunk-size", type=int, help="override BLE write chunk size")
    hex_parser.add_argument("--delay", type=float, default=0.02, help="delay between chunks")
    hex_parser.add_argument("--listen", type=float, default=1.0, help="notification listen time after writing")

    file_parser = subparsers.add_parser("write-file", help="send raw bytes from a file")
    add_connect_args(file_parser)
    file_parser.add_argument("file", type=Path)
    file_parser.add_argument("--strip-leading-nuls", action="store_true")
    file_parser.add_argument("--char", help="write characteristic UUID or suffix")
    file_parser.add_argument("--chunk-size", type=int, help="override BLE write chunk size")
    file_parser.add_argument("--delay", type=float, default=0.02, help="delay between chunks")
    file_parser.add_argument("--file-delay", type=float, default=0.0, help="delay between files")
    file_parser.add_argument("--listen", type=float, default=1.0, help="notification listen time after writing")

    files_parser = subparsers.add_parser("write-files", help="send multiple raw byte files over one BLE connection")
    add_connect_args(files_parser)
    files_parser.add_argument("files", type=Path, nargs="+")
    files_parser.add_argument("--strip-leading-nuls", action="store_true")
    files_parser.add_argument("--char", help="write characteristic UUID or suffix")
    files_parser.add_argument("--chunk-size", type=int, help="override BLE write chunk size")
    files_parser.add_argument("--delay", type=float, default=0.02, help="delay between chunks")
    files_parser.add_argument("--file-delay", type=float, default=0.0, help="delay between files")
    files_parser.add_argument("--listen", type=float, default=1.0, help="notification listen time after writing")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
