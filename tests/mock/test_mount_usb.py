import pytest
import os
from core.mount_usb import MountUsbOperation
from lib.managers.base import CommandResult
from pathlib import Path

def test_mount_usb_operation(mock_manager):
    # Setup resources
    base_path = Path('core/resources')
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / '99-usb-automount.rules').write_text('udev_mount_rule', encoding='utf-8')

    installed_pkgs = set()
    original_run = mock_manager.run
    def mock_run(command, sudo=False):
        if command.startswith("dpkg-query -W -f='${Status}'"):
            pkg = command.split()[-2].strip("'")
            if pkg in installed_pkgs:
                return CommandResult("install ok installed", "", 0)
            return CommandResult("", "", 0)
        if "apt-get install" in command:
            pkg = command.split()[-1]
            installed_pkgs.add(pkg)
            return CommandResult("Setting up...", "", 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run

    op = MountUsbOperation()
    record = op.apply(mock_manager, {})

    assert record.changed is True
    assert mock_manager.read_file("/etc/udev/rules.d/99-usb-automount.rules") == "udev_mount_rule"

    assert record.previousState['packagesInstalled'] is False
    assert record.currentState['packagesInstalled'] is True
    assert record.currentState['udevRuleReady'] is True

    # Idempotency relies on dpkg checking if packages are installed
    def mock_run_installed(command, sudo=False):
        if command.startswith("dpkg-query -W -f='${Status}'"):
            return CommandResult("install ok installed", "", 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run_installed

    record2 = op.apply(mock_manager, {})
    assert record2.changed is False
    assert record2.previousState['packagesInstalled'] is True
    assert record2.previousState['udevRuleReady'] is True
