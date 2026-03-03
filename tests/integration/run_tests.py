#!/usr/bin/env python3
"""Interactive integration test runner.

Runs safe integration tests by default, with explicit opt-in and confirmation
for real-device tests.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from simple_term_menu import TerminalMenu

# Allow importing project modules
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.cmd_manager import SDCardManager  # pylint: disable=wrong-import-position


SAFE_MARKER_EXPRESSION = "integration and not requires_device and not requires_chroot"
NON_DEVICE_MARKER_EXPRESSION = "integration and not requires_device"
DEVICE_MARKER_EXPRESSION = "integration and requires_device"


def runCommand(command: list[str]) -> int:
    """Run command and return exit code."""
    print("\nRunning:")
    print(" ".join(command))
    print("")
    return subprocess.run(command, check=False).returncode


def checkSudo() -> None:
    """Ensure sudo credentials are available."""
    result = subprocess.run(["sudo", "-v"], check=False)
    if result.returncode != 0:
        raise RuntimeError("sudo authentication failed")


def getPythonExecutable() -> str:
    """Return project virtualenv python executable path."""
    pythonPath = PROJECT_ROOT / "env" / "bin" / "python"
    if not pythonPath.exists():
        raise RuntimeError(f"Virtualenv python not found at {pythonPath}")
    return str(pythonPath)


def detectUsbDevices() -> list[dict]:
    """Detect removable USB devices."""
    devices = SDCardManager.detect_usb_devices()
    print("\nDetected removable USB devices:")
    if not devices:
        print("  (none)")
        return []

    for idx, deviceInfo in enumerate(devices, start=1):
        mountStatus = "mounted" if deviceInfo.get("mounted") else "unmounted"
        mountPoints = deviceInfo.get("mountpoints", [])
        mountText = f" [{', '.join(mountPoints)}]" if mountPoints else ""
        print(
            f"  {idx}. {deviceInfo.get('device')} | {deviceInfo.get('size')} | "
            f"{deviceInfo.get('vendor')} {deviceInfo.get('model')} | {mountStatus}{mountText}"
        )
    return devices


def chooseDeviceInteractively(devices: list[dict]) -> str | None:
    """Show interactive menu for detected devices and return selected device path."""
    if not devices:
        return None

    options = [
        (
            f"{dev.get('device')} - {dev.get('size')} "
            f"{dev.get('vendor')} {dev.get('model')}"
        )
        for dev in devices
    ]

    menu = TerminalMenu(options, title="Select device for real-device tests:")
    selectedIndex = menu.show()
    if selectedIndex is None:
        return None

    selectedDevice = devices[int(selectedIndex)]["device"]

    confirmMenu = TerminalMenu(["No", "Yes"], title=f"Confirm testing device {selectedDevice}?")
    confirmed = confirmMenu.show()
    if confirmed != 1:
        return None

    return selectedDevice


def buildPytestBaseCommand(markerExpression: str, extraArgs: list[str]) -> list[str]:
    """Build pytest command in project context."""
    pythonExe = getPythonExecutable()
    return [pythonExe, "-m", "pytest", "-m", markerExpression, *extraArgs]


def runSafeTests(extraArgs: list[str]) -> int:
    """Run safest integration tests (mount/unmount only, no device/chroot)."""
    checkSudo()
    command = buildPytestBaseCommand(SAFE_MARKER_EXPRESSION, extraArgs)
    return runCommand(command)


def runNonDeviceFullTests(extraArgs: list[str]) -> int:
    """Run all non-device integration tests (includes chroot tests)."""
    checkSudo()
    command = buildPytestBaseCommand(NON_DEVICE_MARKER_EXPRESSION, ["--include-chroot-tests", *extraArgs])
    return runCommand(command)


def runDeviceTests(devicePath: str | None, extraArgs: list[str]) -> int:
    """Run real-device integration tests with explicit device option."""
    checkSudo()
    if devicePath:
        command = buildPytestBaseCommand(DEVICE_MARKER_EXPRESSION, [f"--use-real-device={devicePath}", *extraArgs])
    else:
        command = buildPytestBaseCommand(DEVICE_MARKER_EXPRESSION, ["--use-real-device", *extraArgs])
    return runCommand(command)


def parseArgs() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Run integration tests safely")
    parser.add_argument(
        "--mode",
        choices=["menu", "safe", "non-device", "device", "detect"],
        default="menu",
        help="Execution mode"
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Explicit device path for device mode (e.g., /dev/sdb). If omitted, interactive selection is used."
    )
    parser.add_argument(
        "pytestArgs",
        nargs=argparse.REMAINDER,
        help="Additional pytest args, pass after --"
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    os.chdir(PROJECT_ROOT)
    args = parseArgs()
    extraArgs = args.pytestArgs

    print("Running integration tests...")
    print(f"Project root: {PROJECT_ROOT}")

    if args.mode == "detect":
        detectUsbDevices()
        return 0

    if args.mode == "safe":
        return runSafeTests(extraArgs)

    if args.mode == "non-device":
        return runNonDeviceFullTests(extraArgs)

    if args.mode == "device":
        if args.device:
            return runDeviceTests(args.device, extraArgs)
        devices = detectUsbDevices()
        selectedDevice = chooseDeviceInteractively(devices)
        if not selectedDevice:
            print("Cancelled.")
            return 1
        return runDeviceTests(selectedDevice, extraArgs)

    # Interactive menu mode
    options = [
        "Run safest integration tests (mount-only loopback)",
        "Run all non-device integration tests (includes chroot)",
        "Detect removable devices",
        "Run real-device integration tests",
        "Exit"
    ]

    menu = TerminalMenu(options, title="Integration test runner")
    choice = menu.show()

    if choice is None or choice == 4:
        print("No action selected.")
        return 0

    if choice == 0:
        return runSafeTests(extraArgs)

    if choice == 1:
        return runNonDeviceFullTests(extraArgs)

    if choice == 2:
        detectUsbDevices()
        return 0

    devices = detectUsbDevices()
    selectedDevice = chooseDeviceInteractively(devices)
    if not selectedDevice:
        print("Cancelled.")
        return 1

    return runDeviceTests(selectedDevice, extraArgs)


if __name__ == "__main__":
    raise SystemExit(main())
