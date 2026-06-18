#!/usr/bin/env python3
"""
Quick classic Bluetooth serial probe for JADENS thermal printers.

The JD-268BT can appear on macOS as a /dev/cu.JD-268BT_* device after Bluetooth
pairing. This script sends printer-language bytes to that serial port.

Examples:
  python experiments/serial_probe.py list
  python experiments/serial_probe.py test --port /dev/cu.JD-268BT_1234 --lang tspl
  python experiments/serial_probe.py test --port /dev/cu.JD-268BT_1234 --lang escpos
  python experiments/serial_probe.py write-hex --port /dev/cu.JD-268BT_1234 "1B 40 0A"
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: pyserial\n"
        "Install it with:\n"
        "  .venv/bin/python -m pip install -r requirements.txt"
    ) from exc


@dataclass(frozen=True)
class ProbeCommand:
    label: str
    data: bytes


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    bytes_per_row: int
    data: bytes


def escpos_test() -> ProbeCommand:
    return ProbeCommand(
        "ESC/POS text test",
        b"\x1b@"
        b"JADENS SERIAL TEST\n"
        b"If this printed, ESC/POS over Bluetooth serial works.\n\n"
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
            'TEXT 40,40,"3",0,1,1,"JADENS SERIAL TEST"\r\n'
            'TEXT 40,95,"2",0,1,1,"If this printed, TSPL works."\r\n'
            'PRINT 1\r\n'
        ).encode("ascii"),
    )


def tspl_bitmap(raster: Raster, width_mm: int, height_mm: int) -> ProbeCommand:
    header = (
        f"SIZE {width_mm} mm,{height_mm} mm\r\n"
        "GAP 2 mm,0 mm\r\n"
        "DENSITY 8\r\n"
        "SPEED 4\r\n"
        "DIRECTION 1\r\n"
        "CLS\r\n"
        f"BITMAP 0,0,{raster.bytes_per_row},{raster.height},0,"
    ).encode("ascii")
    payload = header + raster.data + b"\r\nPRINT 1\r\n"
    return ProbeCommand(f"TSPL bitmap {raster.width}x{raster.height}", payload)


def tspl_bars(raster: Raster, width_mm: int, height_mm: int) -> ProbeCommand:
    header = (
        f"SIZE {width_mm} mm,{height_mm} mm\r\n"
        "GAP 2 mm,0 mm\r\n"
        "DENSITY 8\r\n"
        "SPEED 4\r\n"
        "DIRECTION 1\r\n"
        "CLS\r\n"
    )

    active: dict[tuple[int, int], list[int]] = {}
    bars: list[tuple[int, int, int, int]] = []

    for y in range(raster.height):
        current = set(_row_runs(raster, y))
        for run in current:
            if run in active:
                active[run][1] += 1
            else:
                active[run] = [y, 1]

        finished = [run for run in active if run not in current]
        for run in finished:
            start_y, height = active.pop(run)
            bars.append((run[0], start_y, run[1], height))

    for run, (start_y, height) in list(active.items()):
        bars.append((run[0], start_y, run[1], height))

    body = "".join(f"BAR {x},{y},{width},{height}\r\n" for x, y, width, height in bars)
    payload = (header + body + "PRINT 1\r\n").encode("ascii")
    return ProbeCommand(f"TSPL BAR raster {raster.width}x{raster.height}, {len(bars)} bars", payload)


def _row_runs(raster: Raster, y: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    row_offset = y * raster.bytes_per_row
    x = 0
    while x < raster.width:
        byte = raster.data[row_offset + (x // 8)]
        is_black = bool(byte & (0x80 >> (x & 7)))
        if not is_black:
            x += 1
            continue

        start = x
        x += 1
        while x < raster.width:
            byte = raster.data[row_offset + (x // 8)]
            if not (byte & (0x80 >> (x & 7))):
                break
            x += 1
        runs.append((start, x - start))
    return runs


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
    return bytes(int(token, 16) for token in tokens)


def hex_preview(data: bytes, limit: int = 96) -> str:
    prefix = " ".join(f"{byte:02X}" for byte in data[:limit])
    if len(data) > limit:
        return f"{prefix} ... (+{len(data) - limit} bytes)"
    return prefix


def list_serial_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return 0

    for port in ports:
        marker = "  <-- likely JADENS" if "JD-268BT" in port.device or "JADENS" in port.device.upper() else ""
        print(f"{port.device:<32} {port.description}{marker}")
    return 0


def send_to_port(args: argparse.Namespace, command: ProbeCommand) -> int:
    port = Path(args.port)
    if not port.exists():
        print(f"Serial port does not exist: {port}", file=sys.stderr)
        return 2

    print(f"Opening {port} at {args.baudrate} baud...")
    print(f"Sending {command.label}: {len(command.data)} bytes")
    print(f"Preview: {hex_preview(command.data)}")

    sent = 0
    next_progress = args.progress_bytes if args.progress_bytes > 0 else 0

    with serial.Serial(
        str(port),
        baudrate=args.baudrate,
        timeout=args.timeout,
        write_timeout=args.timeout,
        rtscts=False,
        dsrdtr=False,
    ) as connection:
        for offset in range(0, len(command.data), args.chunk_size):
            chunk = command.data[offset : offset + args.chunk_size]
            sent += connection.write(chunk)
            if args.flush_each_chunk:
                connection.flush()
            if next_progress and sent >= next_progress:
                print(f"Wrote {sent}/{len(command.data)} bytes", flush=True)
                while next_progress <= sent:
                    next_progress += args.progress_bytes
            if args.delay:
                time.sleep(args.delay)

        if not args.skip_final_flush:
            connection.flush()

        if args.read:
            time.sleep(args.read)
            waiting = connection.in_waiting
            if waiting:
                response = connection.read(waiting)
                print(f"Read {len(response)} byte(s): {hex_preview(response)}")
            else:
                print("No response bytes available.")

    return 0


def rasterize_file(
    path: Path,
    width: int,
    height: int,
    threshold: int,
    rotate: int,
    invert: bool,
) -> Raster:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if threshold < 0 or threshold > 255:
        raise ValueError("threshold must be between 0 and 255")
    if rotate not in {0, 90, 180, 270}:
        raise ValueError("rotate must be one of 0, 90, 180, 270")
    if not path.exists():
        raise FileNotFoundError(path)

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Missing Pillow. Run: .venv/bin/python -m pip install -r requirements.txt") from exc

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Missing PyMuPDF. Run: .venv/bin/python -m pip install -r requirements.txt") from exc

        document = fitz.open(path)
        if document.page_count < 1:
            raise ValueError("PDF has no pages")
        page = document.load_page(0)
        page_rect = page.rect
        source_width = page_rect.height if rotate in {90, 270} else page_rect.width
        source_height = page_rect.width if rotate in {90, 270} else page_rect.height
        scale = min(width / source_width, height / source_height)
        matrix = fitz.Matrix(scale, scale).prerotate(rotate)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    else:
        image = Image.open(path).convert("RGB")
        if rotate:
            image = image.rotate(-rotate, expand=True)

    image = ImageOps.grayscale(image)
    image.thumbnail((width, height), Image.Resampling.LANCZOS)

    canvas = Image.new("L", (width, height), 255)
    left = (width - image.width) // 2
    top = (height - image.height) // 2
    canvas.paste(image, (left, top))

    if invert:
        canvas = ImageOps.invert(canvas)

    pixels = canvas.tobytes()
    bytes_per_row = (width + 7) // 8
    packed = bytearray(bytes_per_row * height)

    for y in range(height):
        row_offset = y * width
        packed_row_offset = y * bytes_per_row
        for x in range(width):
            if pixels[row_offset + x] < threshold:
                packed[packed_row_offset + (x // 8)] |= 0x80 >> (x & 7)

    return Raster(width=width, height=height, bytes_per_row=bytes_per_row, data=bytes(packed))


def print_file(args: argparse.Namespace) -> int:
    raster = rasterize_file(
        args.file,
        width=args.width_dots,
        height=args.height_dots,
        threshold=args.threshold,
        rotate=args.rotate,
        invert=args.invert,
    )
    if args.method == "bitmap":
        command = tspl_bitmap(raster, width_mm=args.width_mm, height_mm=args.height_mm)
    elif args.method == "bars":
        command = tspl_bars(raster, width_mm=args.width_mm, height_mm=args.height_mm)
    else:
        raise ValueError(f"unknown method: {args.method}")

    print(
        f"Rasterized {args.file} to {raster.width}x{raster.height}, "
        f"{raster.bytes_per_row} bytes/row, {len(raster.data)} bitmap bytes"
    )
    if args.dry_run:
        print(f"Dry run. Would send {len(command.data)} bytes.")
        print(f"Preview: {hex_preview(command.data)}")
        return 0

    return send_to_port(args, command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list serial ports")

    def add_write_args(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--port", default="/dev/cu.JD-268BT_1234")
        command_parser.add_argument("--baudrate", type=int, default=115200)
        command_parser.add_argument("--timeout", type=float, default=3.0)
        command_parser.add_argument("--chunk-size", type=int, default=512)
        command_parser.add_argument("--delay", type=float, default=0.02)
        command_parser.add_argument("--read", type=float, default=0.5, help="seconds to wait for response bytes")
        command_parser.add_argument("--flush-each-chunk", action="store_true")
        command_parser.add_argument("--skip-final-flush", action="store_true")
        command_parser.add_argument("--progress-bytes", type=int, default=16_384)

    test_parser = subparsers.add_parser("test", help="send a small printer-language test")
    add_write_args(test_parser)
    test_parser.add_argument("--lang", choices=["tspl", "escpos"], default="tspl")

    hex_parser = subparsers.add_parser("write-hex", help="send raw hex bytes")
    add_write_args(hex_parser)
    hex_parser.add_argument("hex_bytes")

    print_parser = subparsers.add_parser("print-file", help="rasterize a PDF/image and print it as TSPL BITMAP")
    add_write_args(print_parser)
    print_parser.set_defaults(chunk_size=1024)
    print_parser.add_argument("file", type=Path)
    print_parser.add_argument("--width-dots", type=int, default=812, help="4 inch at 203 DPI")
    print_parser.add_argument("--height-dots", type=int, default=1218, help="6 inch at 203 DPI")
    print_parser.add_argument("--width-mm", type=int, default=100)
    print_parser.add_argument("--height-mm", type=int, default=150)
    print_parser.add_argument("--threshold", type=int, default=160)
    print_parser.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0)
    print_parser.add_argument("--invert", action="store_true")
    print_parser.add_argument("--method", choices=["bitmap", "bars"], default="bitmap")
    print_parser.add_argument("--dry-run", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "list":
            return list_serial_ports()
        if args.command == "test":
            command = tspl_test() if args.lang == "tspl" else escpos_test()
            return send_to_port(args, command)
        if args.command == "write-hex":
            return send_to_port(args, ProbeCommand("raw hex", parse_hex(args.hex_bytes)))
        if args.command == "print-file":
            return print_file(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise ValueError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
