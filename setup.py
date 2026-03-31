"""
py2app packaging script for WHOOP Live.

Build command:
    python setup.py py2app

Output: dist/WHOOP Live.app
"""
from setuptools import setup

APP      = ["server.py"]
APP_NAME = "WHOOP Live"

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "AppIcon.icns",
    "plist": {
        "CFBundleName":             APP_NAME,
        "CFBundleDisplayName":      APP_NAME,
        "CFBundleIdentifier":       "com.whooplive.app",
        "CFBundleVersion":          "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "NSBluetoothAlwaysUsageDescription":
            "WHOOP Live needs Bluetooth to read heart rate from your WHOOP strap.",
        "NSBluetoothPeripheralUsageDescription":
            "WHOOP Live needs Bluetooth to read heart rate from your WHOOP strap.",
        "NSHighResolutionCapable": True,
    },
    "packages": [
        "flask", "bleak", "webview",
        "werkzeug", "jinja2", "click",
        "bleak.backends", "bleak.backends.corebluetooth",
    ],
    "excludes": ["tkinter", "PyQt5", "wx"],
    "semi_standalone": False,
    "site_packages": True,
}

setup(
    app=APP,
    name=APP_NAME,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
