# JADENS BLE Printer App

A local macOS printer app for the JADENS JD-268BT Bluetooth LE label printer.
It lets normal macOS print dialogs target a local IPP queue, then forwards the
rendered label stream to the printer over BLE.

This project is not affiliated with or endorsed by JADENS.

This project does not implement a custom JADENS raster encoder. The working
path uses the vendor macOS driver package for PDF-to-label conversion, then
sends the vendor-generated printer stream over the confirmed BLE write
characteristic.

## Current Print Path

```text
macOS app print dialog
  -> CUPS queue: Jadens_268BT_BLE
  -> local IPP server: ippeveprinter on localhost:8631
  -> JadensIPPCommand
  -> /Library/Printers/Jadens/Filter/rastertolabel
  -> BLEProbe.app
  -> JD-268BT* characteristic 0000fff2-0000-1000-8000-00805f9b34fb
```

The installed runtime lives at:

```text
~/Library/Application Support/JadensPrinterApp
```

The printer service starts at user login through:

```text
~/Library/LaunchAgents/com.kancharlawar.jadensprinter.plist
```

## Package for Another Mac

Build the release bundle and double-click installer:

```sh
./packaging/package_release.sh
```

This creates:

```text
dist/JadensPrinterApp-0.1.2/
dist/JadensPrinterApp-0.1.2.pkg
```

On another Apple Silicon Mac, open:

```text
JadensPrinterApp-0.1.2.pkg
```

The package runs through the normal macOS Installer UI. It copies the app
payload, downloads and installs the official JADENS macOS driver if needed,
starts the `JadensPrinterService` LaunchAgent, creates the `Jadens_268BT_BLE`
queue, and launches `BLEProbe.app` once so macOS can ask for Bluetooth
permission.

The first install requires internet access if the JADENS driver is not already
installed. The downloaded driver package is verified against a pinned SHA-256
checksum before it is installed.

The package is unsigned. Use control-click -> Open if Gatekeeper blocks a normal
double-click.

This release is Apple Silicon only because the packaged helper binaries are
built as `arm64`.

## What We Validated

Working:

- BLE device matching is by name substring: `JD-268BT`.
  The tested unit advertised as `JD-268BT_4967-LE`.
- Writable BLE print characteristic:
  `0000fff2-0000-1000-8000-00805f9b34fb`.
- A TSPL text command printed over BLE.
- The JADENS macOS driver installs:
  `/Library/Printers/Jadens/Filter/rastertolabel`.
- A PDF page rendered through `rastertolabel` printed when sent over BLE.
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
JADENS_BLE_DELAY=0.01
JADENS_BLE_FILE_DELAY=0.05
JADENS_BLE_LISTEN=0.25
```

If labels print reliably, lower `JADENS_BLE_DELAY` to increase throughput. If
labels are incomplete or skipped, raise it.

## More Detail

See `docs/implementation-notes.md` for the confirmed device details, shipped
components, and the paths that were tried but not used.
