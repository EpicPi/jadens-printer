# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["../src/ble_probe.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BLEProbe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BLEProbe",
)

app = BUNDLE(
    coll,
    name="BLEProbe.app",
    icon=None,
    bundle_identifier="com.kancharlawar.jadensprinter.bleprobe",
    info_plist={
        "CFBundleName": "Jadens BLE Probe",
        "NSBluetoothAlwaysUsageDescription": "JADENS Printer App uses Bluetooth to find and connect to JD-268BT label printers for printing.",
        "NSBluetoothPeripheralUsageDescription": "JADENS Printer App uses Bluetooth to find and connect to JD-268BT label printers for printing.",
    },
)
