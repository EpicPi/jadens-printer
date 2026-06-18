# JADENS JD-268BT macOS Printer App

Print from macOS to a JADENS JD-268BT Bluetooth label printer.

This adds a normal Mac printer option for the JD-268BT, so you can print labels
from apps like Preview, Safari, Chrome, or any app with a macOS print dialog.
You do not need to move PDFs to the mobile app just to print them.

## Download

Installable packages are attached to
[GitHub Releases](https://github.com/EpicPi/jadens-printer/releases). Download
the latest `JadensPrinterApp-<version>.pkg` asset and open it on an Apple
Silicon Mac.

Turn on the printer and connect it in macOS Bluetooth settings. If macOS asks
for a PIN, try `0000` or `1234`.

After installing, choose `Jadens_268BT_BLE` from a normal macOS print dialog.
macOS may ask for Bluetooth permission the first time the helper app runs.

The first install requires internet access if the JADENS driver is not already
installed.

The package is unsigned. Use control-click -> Open if Gatekeeper blocks a normal
double-click.

This project is not affiliated with or endorsed by JADENS.

## Technical Details

The app installs a local printer queue that appears in normal macOS print
dialogs. It uses the official JADENS macOS driver package for PDF-to-label
conversion, then sends the printer-ready output to the JD-268BT over Bluetooth
LE.

It does not implement a custom JADENS raster encoder. The installer downloads
and installs the official JADENS macOS driver if needed, then verifies the
expected driver files are present.

The driver files used by the app are:

```text
/Library/Printers/Jadens/PPDs/JD-268BT.ppd
/Library/Printers/Jadens/Filter/rastertolabel
```

`rastertolabel` converts CUPS raster into the compact command stream accepted
by the printer. Its output included leading NUL bytes during testing; the app
strips those before writing to BLE.

This release is Apple Silicon only because the packaged helper binaries are
built as `arm64`.

### Current Print Path

```text
macOS app print dialog
  -> CUPS queue: Jadens_268BT_BLE
  -> local IPP server: ippeveprinter on localhost:8631
  -> JadensIPPCommand
  -> /Library/Printers/Jadens/Filter/rastertolabel
  -> BLEProbe.app
  -> JD-268BT* characteristic 0000fff2-0000-1000-8000-00805f9b34fb
```

For each print job, `JadensIPPCommand` renders every PDF page, converts each
page to CUPS raster with `cupsfilter`, runs each raster page through
`rastertolabel`, then sends all page payloads over one BLE connection.

The installed runtime lives at:

```text
~/Library/Application Support/JadensPrinterApp
```

The printer service starts at user login through:

```text
~/Library/LaunchAgents/com.kancharlawar.jadensprinter.plist
```

The installer removes partial previous installs before copying new files. It
unloads the old LaunchAgent, removes the old queue, stops stale `ippeveprinter`
processes, deletes the old app directory, then installs the fresh runtime.

## Build Locally

Create a local release bundle and installer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./packaging/package_release.sh
```

This creates:

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

## Publishing Releases

`VERSION` is the release version source of truth. When `VERSION` changes on
`main`, GitHub Actions builds `dist/JadensPrinterApp-<version>.pkg` on an
Apple Silicon macOS runner and publishes it to the GitHub Release tagged
`v<version>`.

## What We Validated

Working:

- BLE device matching is by name substring: `JD-268BT`.
  The tested unit advertised as `JD-268BT_4967-LE`.
- Writable BLE print characteristic:
  `0000fff2-0000-1000-8000-00805f9b34fb`.
- Notify characteristic observed during GATT discovery:
  `0000fff1-0000-1000-8000-00805f9b34fb`.
- A TSPL text command printed over BLE.
- The JADENS macOS driver installs both expected files:
  `/Library/Printers/Jadens/PPDs/JD-268BT.ppd` and
  `/Library/Printers/Jadens/Filter/rastertolabel`.
- A PDF page rendered through `rastertolabel` printed when sent over BLE
  `FFF2`.
- A local IPP queue can make this selectable from normal macOS print dialogs.
- Multi-page jobs now send all page payloads over one BLE connection.

Not used in the shipped path:

- Classic Bluetooth serial at `/dev/cu.JD-268BT_*`; it accepted writes but
  did not reliably print.
- macOS's native Bluetooth printer setup; CUPS could not create a reliable
  working printer destination for this device.

## Local Commands

Print one PDF page directly over BLE:

```sh
./debug/print_pdf_page_ble.sh /path/to/label.pdf 1
```

Start the local IPP printer app manually:

```sh
./debug/start_printer_app.sh
```

Then add the queue manually:

```sh
lpadmin -p Jadens_268BT_BLE -E -v ipp://localhost:8631/ipp/print -m everywhere
```

The packaged installer performs those setup steps automatically.

Runtime defaults can be overridden with environment variables when launching the
debug service directly:

```text
JADENS_BLE_NAME=JD-268BT
JADENS_DEVICE_URI=jadensble://JD-268BT
JADENS_QUEUE_NAME=Jadens_268BT_BLE
JADENS_IPP_PORT=8631
```

## BLE Probe

The BLE probe is kept for verification and debugging:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/ble_probe.py scan --name JD-268BT
.venv/bin/python src/ble_probe.py gatt --name JD-268BT
```

On macOS, the packaged app form is preferred because it includes a Bluetooth
usage description:

```sh
.venv/bin/python -m pip install pyinstaller
./packaging/build_ble_probe_app.sh
./src/run_ble_probe_app.sh scan --name JD-268BT
```

TSPL smoke test:

```sh
./src/run_ble_probe_app.sh test --name JD-268BT --lang tspl
```

## Speed Tuning

The default write pacing is conservative:

```text
JADENS_BLE_DELAY=0.005
JADENS_BLE_FILE_DELAY=0.02
JADENS_BLE_LISTEN=0.25
```

If labels print reliably, lower `JADENS_BLE_DELAY` to increase throughput. If
labels are incomplete or skipped, raise it.
