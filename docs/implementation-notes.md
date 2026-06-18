# Implementation Notes

These notes document what was actually validated while building the JADENS
macOS printer app. The final implementation relies on the vendor macOS driver
for raster generation and uses BLE only as the transport to the printer.

## Confirmed Device Details

- BLE name matching is by substring: `JD-268BT`.
- The tested unit advertised as `JD-268BT_4967-LE`.
- Working BLE write characteristic:
  `0000fff2-0000-1000-8000-00805f9b34fb`.
- Notify characteristic observed during GATT discovery:
  `0000fff1-0000-1000-8000-00805f9b34fb`.
- TSPL text printed successfully over BLE.
- A vendor-rendered raw label stream printed successfully over BLE `FFF2`.

## Vendor Driver Files

The JADENS macOS driver package installs the files used by the app:

```text
/Library/Printers/Jadens/PPDs/JD-268BT.ppd
/Library/Printers/Jadens/Filter/rastertolabel
```

`rastertolabel` converts CUPS raster into the compact command stream accepted by
the printer. Its output included leading NUL bytes during testing; the app
strips those before writing to BLE.

The installer downloads the official JADENS macOS driver package when those
files are missing, verifies its SHA-256 checksum, installs it with Apple's
`installer`, then checks for the files above.

## Working PDF Flow

For each print job:

1. `ippeveprinter` receives the PDF from CUPS.
2. `JadensIPPCommand` counts and renders the pages.
3. Each page is converted to CUPS raster with `cupsfilter`.
4. Each raster page is converted with the vendor `rastertolabel` filter.
5. All page payloads are sent over one BLE connection through `BLEProbe.app`.

The direct single-page helper is:

```sh
./debug/print_pdf_page_ble.sh /path/to/label.pdf 1
```

## Local Printer App

`debug/start_printer_app.sh` starts Apple's `ippeveprinter` on localhost:

```sh
./debug/start_printer_app.sh
```

The CUPS queue points at:

```text
ipp://localhost:8631/ipp/print
```

The installed package uses `JadensPrinterService` as the LaunchAgent entrypoint.
That binary starts `ippeveprinter` with `JadensIPPCommand` as the print command.

## Release Package Contents

`packaging/package_release.sh` builds:

```text
dist/JadensPrinterApp-$(cat VERSION)/
dist/JadensPrinterApp-$(cat VERSION).pkg
```

The release payload contains:

- `BLEProbe.app`: CoreBluetooth helper with Bluetooth usage metadata.
- `JadensPrinterService`: LaunchAgent entrypoint for the local IPP server.
- `JadensIPPCommand`: print command that renders PDF pages and sends raw BLE
  payloads.
- `run_ble_probe_app.sh`: helper used by the installer to trigger the
  Bluetooth permission prompt.

Debug helpers live under `debug/`, and exploratory scripts live under
`experiments/`. They are not included in the release payload.

The installer removes partial previous installs before copying new files. It
unloads the old LaunchAgent, removes the old queue, stops stale `ippeveprinter`
processes, deletes the old app directory, then installs the fresh runtime.

GitHub Actions builds the unsigned Apple Silicon package when `VERSION` changes
on `main`, then attaches the package to the GitHub Release tagged `v<version>`.

## Paths Tried But Not Shipped

Classic Bluetooth serial:

- macOS exposed a `/dev/cu.JD-268BT_*` serial device.
- Writes to that device did not reliably print.
- It is kept only as a reference/debug script path.

Native macOS Bluetooth printer setup:

- macOS could see the Bluetooth printer-class device.
- The CUPS Bluetooth backend did not create a working destination for this
  printer in testing.
- The shipped path uses a local IPP queue instead.

## Tuning

BLE write pacing defaults:

```text
JADENS_BLE_DELAY=0.01
JADENS_BLE_FILE_DELAY=0.05
JADENS_BLE_LISTEN=0.25
```

Lower `JADENS_BLE_DELAY` for more throughput. Raise it if labels are incomplete
or skipped.
