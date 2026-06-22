#!/usr/bin/env python3
"""
ippeveprinter command for the JD-268BT BLE printer application.

ippeveprinter invokes this command for each submitted document. The command
expects a PDF spool file, renders each page through the installed JADENS driver
filter, then sends the compact raw page stream over BLE characteristic FFF2.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import io
import time
from argparse import Namespace
from collections.abc import Mapping
from contextlib import redirect_stdout
from pathlib import Path


def detect_app_root() -> Path:
    if "JADENS_APP_ROOT" in os.environ:
        return Path(os.environ["JADENS_APP_ROOT"]).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[1]


ROOT = detect_app_root()
DEFAULT_BLE_NAME = "JD-268BT"
DEFAULT_BLE_CHAR = "0000fff2-0000-1000-8000-00805f9b34fb"
DEFAULT_PAGE_SIZE = "w288h432"
CUSTOM_WIDTH_MIN_POINTS = 36
CUSTOM_WIDTH_MAX_POINTS = 294
CUSTOM_HEIGHT_MIN_POINTS = 36
CUSTOM_HEIGHT_MAX_POINTS = 5670
POINTS_PER_INCH = 72
IPP_UNITS_PER_INCH = 2540
COMMAND_LOG = Path(os.environ.get("JADENS_LOG_FILE", ROOT / "logs/ipp-jadens-command.log"))

VENV_PYTHON = ROOT / ".venv/bin/python"
if (
    not getattr(sys, "frozen", False)
    and VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def log(prefix: str, message: str) -> None:
    print(f"{prefix}: {message}", file=sys.stderr, flush=True)
    COMMAND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COMMAND_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}: {message}\n")


def run(command: list[str]) -> None:
    log("DEBUG", "running " + " ".join(command))
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.stdout:
        for line in result.stdout.splitlines():
            log("INFO", line)
    if result.stderr:
        for line in result.stderr.splitlines():
            log("INFO" if result.returncode == 0 else "ERROR", line)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")


def pdf_page_count(pdf: Path) -> int:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Missing PyMuPDF. Run .venv/bin/python -m pip install -r requirements.txt") from exc

    document = fitz.open(pdf)
    return document.page_count


def spool_file_from_args(argv: list[str]) -> Path:
    if len(argv) >= 2 and argv[1] != "-":
        candidate = Path(argv[1]).resolve()
        if candidate.exists():
            return candidate

    if len(argv) >= 7 and argv[6] != "-":
        return Path(argv[6]).resolve()

    fd, temp_name = tempfile.mkstemp(prefix="jadens-ipp-stdin-", suffix=".pdf")
    with os.fdopen(fd, "wb") as temp_file:
        temp_file.write(sys.stdin.buffer.read())
    return Path(temp_name)


def copies_from_args(argv: list[str]) -> int:
    if len(argv) >= 5:
        try:
            return max(1, int(argv[4]))
        except ValueError:
            return 1
    return 1


def points_from_ipp_dimension(value: int) -> int:
    return round(value * POINTS_PER_INCH / IPP_UNITS_PER_INCH)


def points_from_named_dimension(value: str, unit: str) -> int:
    numeric = float(value)
    normalized = unit.lower()
    if normalized == "in":
        return round(numeric * POINTS_PER_INCH)
    if normalized == "mm":
        return round(numeric * POINTS_PER_INCH / 25.4)
    if normalized == "cm":
        return round(numeric * POINTS_PER_INCH / 2.54)
    raise ValueError(f"unsupported media unit: {unit}")


def custom_page_size(width_points: int, height_points: int) -> str:
    if width_points == 288 and height_points == 432:
        return DEFAULT_PAGE_SIZE

    if not CUSTOM_WIDTH_MIN_POINTS <= width_points <= CUSTOM_WIDTH_MAX_POINTS:
        raise ValueError(
            f"custom media width {width_points}pt is outside supported range "
            f"{CUSTOM_WIDTH_MIN_POINTS}-{CUSTOM_WIDTH_MAX_POINTS}pt"
        )
    if not CUSTOM_HEIGHT_MIN_POINTS <= height_points <= CUSTOM_HEIGHT_MAX_POINTS:
        raise ValueError(
            f"custom media height {height_points}pt is outside supported range "
            f"{CUSTOM_HEIGHT_MIN_POINTS}-{CUSTOM_HEIGHT_MAX_POINTS}pt"
        )
    return f"Custom.{width_points}x{height_points}"


def page_size_from_media_keyword(media: str) -> str | None:
    value = media.strip().strip('"')
    if value in {"", "none"}:
        return None
    if value in {DEFAULT_PAGE_SIZE, "na_index-4x6_4x6in"}:
        return DEFAULT_PAGE_SIZE

    token_match = re.fullmatch(r"(?i)custom[._-](\d+)x(\d+)", value)
    if token_match:
        return custom_page_size(int(token_match.group(1)), int(token_match.group(2)))

    size_match = re.search(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(in|mm|cm)(?:$|[^a-z0-9])", value, re.IGNORECASE)
    if size_match:
        width = points_from_named_dimension(size_match.group(1), size_match.group(3))
        height = points_from_named_dimension(size_match.group(2), size_match.group(3))
        return custom_page_size(width, height)

    return None


def page_size_from_media_col(value: str) -> str | None:
    x_match = re.search(r"x-dimension\s*=\s*(\d+)", value)
    y_match = re.search(r"y-dimension\s*=\s*(\d+)", value)
    if not x_match or not y_match:
        name_match = re.search(r'(?:media-size-name|media-key)\s*=\s*"?([^"\s}]+)', value)
        if name_match:
            return page_size_from_media_keyword(name_match.group(1))
        return None

    width = points_from_ipp_dimension(int(x_match.group(1)))
    height = points_from_ipp_dimension(int(y_match.group(1)))
    return custom_page_size(width, height)


def page_size_from_job_env(env: Mapping[str, str]) -> str:
    for x_key, y_key in (
        ("IPP_MEDIA_COL_MEDIA_SIZE_X_DIMENSION", "IPP_MEDIA_COL_MEDIA_SIZE_Y_DIMENSION"),
        ("IPP_MEDIA_SIZE_X_DIMENSION", "IPP_MEDIA_SIZE_Y_DIMENSION"),
    ):
        if env.get(x_key) and env.get(y_key):
            width = points_from_ipp_dimension(int(env[x_key]))
            height = points_from_ipp_dimension(int(env[y_key]))
            return custom_page_size(width, height)

    for key in ("IPP_MEDIA_COL", "IPP_MEDIA_SIZE"):
        value = env.get(key)
        if value:
            page_size = page_size_from_media_col(value)
            if page_size:
                return page_size

    media = env.get("IPP_MEDIA")
    if media:
        page_size = page_size_from_media_keyword(media)
        if page_size:
            return page_size
        raise ValueError(f"unsupported requested media: {media}")

    return DEFAULT_PAGE_SIZE


def prepare_page(pdf: Path, page: int, output: Path, page_size: str) -> None:
    from prepare_jadens_raw import DEFAULT_FILTER, DEFAULT_PPD, prepare_raw

    log("DEBUG", f"preparing {pdf} page {page} -> {output} page_size={page_size}")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        prepare_raw(
            Namespace(
                pdf=pdf,
                page=page,
                output=output,
                page_size=page_size,
                ppd=Path(os.environ.get("JADENS_PPD", DEFAULT_PPD)),
                filter=Path(os.environ.get("JADENS_FILTER", DEFAULT_FILTER)),
                strip_leading_nuls=True,
            )
        )
    for line in buffer.getvalue().splitlines():
        log("INFO", line)


def send_raws(raws: list[Path]) -> None:
    if not raws:
        return

    ble_app = Path(
        os.environ.get(
            "JADENS_BLE_APP",
            str(ROOT / "apps/BLEProbe.app")
            if (ROOT / "apps/BLEProbe.app").exists()
            else str(ROOT / "build/python-probe/BLEProbe.app"),
        )
    )
    if not ble_app.exists():
        raise FileNotFoundError(f"BLEProbe.app not found at {ble_app}")

    with tempfile.TemporaryDirectory(prefix="jadens-ble-open-") as temp_dir:
        out = Path(temp_dir) / "bleprobe.out"
        err = Path(temp_dir) / "bleprobe.err"
        command = [
            "open",
            "-W",
            "-n",
            "-o",
            str(out),
            "--stderr",
            str(err),
            str(ble_app),
            "--args",
            "--timeout",
            os.environ.get("JADENS_BLE_TIMEOUT", "10"),
            "write-files",
            "--name",
            os.environ.get("JADENS_BLE_NAME", DEFAULT_BLE_NAME),
            "--char",
            os.environ.get("JADENS_BLE_CHAR", DEFAULT_BLE_CHAR),
            "--chunk-size",
            os.environ.get("JADENS_BLE_CHUNK_SIZE", "180"),
            "--delay",
            os.environ.get("JADENS_BLE_DELAY", "0.005"),
            "--file-delay",
            os.environ.get("JADENS_BLE_FILE_DELAY", "2.0"),
            "--listen",
            os.environ.get("JADENS_BLE_LISTEN", "0.25"),
            *[str(raw) for raw in raws],
        ]
        run(command)
        if out.exists():
            for line in out.read_text(errors="replace").splitlines():
                log("INFO", line)
        if err.exists():
            for line in err.read_text(errors="replace").splitlines():
                log("ERROR", line)


def send_raw(raw: Path) -> None:
    send_raws([raw])


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] in {"--self-test", "--version"}:
        print("JadensIPPCommand OK")
        print(f"app_root={ROOT}")
        print(f"log={COMMAND_LOG}")
        print(f"frozen={bool(getattr(sys, 'frozen', False))}")
        return 0

    try:
        content_type = os.environ.get("CONTENT_TYPE", "unknown")
        pdf = spool_file_from_args(argv)
        copies = copies_from_args(argv)
        pages = pdf_page_count(pdf)
        page_size = page_size_from_job_env(os.environ)

        if content_type not in {"application/pdf", "unknown"}:
            log("INFO", f"received CONTENT_TYPE={content_type}; attempting PDF handling")

        log("INFO", f"printing {pdf.name}: pages={pages} copies={copies} page_size={page_size}")
        print("STATE: +connecting-to-device", file=sys.stderr, flush=True)

        job_start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="jadens-ipp-raw-") as temp_dir:
            temp_path = Path(temp_dir)
            prepared_pages: list[Path] = []

            render_start = time.monotonic()
            for page in range(1, pages + 1):
                raw = temp_path / f"page-{page}.raw"
                log("INFO", f"rendering page {page}/{pages}")
                prepare_page(pdf, page, raw, page_size)
                prepared_pages.append(raw)
            log("INFO", f"rendered {pages} page(s) in {time.monotonic() - render_start:.2f}s")

            raw_job: list[Path] = []
            for _copy_index in range(1, copies + 1):
                raw_job.extend(prepared_pages)

            log("INFO", f"sending {len(raw_job)} page payload(s) over one BLE connection")
            send_start = time.monotonic()
            send_raws(raw_job)
            log("INFO", f"sent {len(raw_job)} page payload(s) in {time.monotonic() - send_start:.2f}s")
            print(f"ATTR: job-impressions-completed={len(raw_job)}", file=sys.stderr, flush=True)

        print("STATE: -connecting-to-device", file=sys.stderr, flush=True)
        log("INFO", f"job complete in {time.monotonic() - job_start:.2f}s")
        return 0
    except Exception as exc:
        print("STATE: +stopped", file=sys.stderr, flush=True)
        log("ERROR", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
