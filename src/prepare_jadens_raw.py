#!/usr/bin/env python3
"""
Render one PDF page through the installed JADENS CUPS filter.

This produces the compact TSPL/raster byte stream that the JD-268BT accepts over
BLE characteristic 0000fff2-0000-1000-8000-00805f9b34fb.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


DEFAULT_PPD = Path("/Library/Printers/Jadens/PPDs/JD-268BT.ppd")
DEFAULT_FILTER = Path("/Library/Printers/Jadens/Filter/rastertolabel")


def extract_pdf_page(source: Path, page_number: int, output: Path) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Missing PyMuPDF. Run: .venv/bin/python -m pip install -r requirements.txt") from exc

    document = fitz.open(source)
    if page_number < 1 or page_number > document.page_count:
        raise ValueError(f"page must be between 1 and {document.page_count}; got {page_number}")

    one_page = fitz.open()
    one_page.insert_pdf(document, from_page=page_number - 1, to_page=page_number - 1)
    one_page.save(output)


def run_checked(command: list[str], *, stdout_path: Path | None = None, env: dict[str, str] | None = None) -> None:
    if stdout_path is None:
        result = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    else:
        with stdout_path.open("wb") as stdout:
            result = subprocess.run(command, text=True, stderr=subprocess.PIPE, stdout=stdout, env=env, check=False)

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{stderr}")


def prepare_raw(args: argparse.Namespace) -> Path:
    source = args.pdf.resolve()
    ppd = args.ppd.resolve()
    filter_path = args.filter.resolve()
    output = args.output.resolve()

    if not source.exists():
        raise FileNotFoundError(source)
    if not ppd.exists():
        raise FileNotFoundError(f"JADENS PPD not found: {ppd}")
    if not filter_path.exists():
        raise FileNotFoundError(f"JADENS rastertolabel filter not found: {filter_path}")

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="jadens-raw-") as temp_dir:
        temp_path = Path(temp_dir)
        page_pdf = temp_path / "page.pdf"
        cups_raster = temp_path / "page.cupsraster"
        raw_with_prefix = temp_path / "page.raw"

        extract_pdf_page(source, args.page, page_pdf)

        run_checked(
            [
                "cupsfilter",
                "-m",
                "application/vnd.cups-raster",
                "-p",
                str(ppd),
                "-o",
                f"PageSize={args.page_size}",
                str(page_pdf),
            ],
            stdout_path=cups_raster,
        )

        env = os.environ.copy()
        env["PPD"] = str(ppd)
        run_checked(
            [
                str(filter_path),
                "1",
                os.environ.get("USER", "user"),
                source.name,
                "1",
                f"PageSize={args.page_size}",
                str(cups_raster),
            ],
            stdout_path=raw_with_prefix,
            env=env,
        )

        raw = raw_with_prefix.read_bytes()
        leading_nuls = len(raw) - len(raw.lstrip(b"\x00"))
        if args.strip_leading_nuls:
            raw = raw.lstrip(b"\x00")
        output.write_bytes(raw)

    print(f"wrote {output}")
    print(f"bytes={output.stat().st_size} page={args.page} page_size={args.page_size}")
    if leading_nuls:
        action = "stripped" if args.strip_leading_nuls else "kept"
        print(f"leading_nuls={leading_nuls} {action}")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1, help="1-based page number")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page-size", default="w288h432", help="PPD PageSize token for 4x6 labels")
    parser.add_argument("--ppd", type=Path, default=DEFAULT_PPD)
    parser.add_argument("--filter", type=Path, default=DEFAULT_FILTER)
    parser.add_argument("--strip-leading-nuls", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        prepare_raw(args)
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
