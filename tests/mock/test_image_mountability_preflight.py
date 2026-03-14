"""Mock tests for ImageFileManager mountability preflight behavior."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import ImageFileManager
from lib.managers.base import CommandResult


@pytest.mark.mock
def test_preflight_rejects_network_backed_image():
    """Network-backed image paths should fail before losetup probe."""
    manager = ImageFileManager.__new__(ImageFileManager)

    manager._is_network_mounted_path = lambda path: True
    manager._run_local = lambda command, sudo=False: CommandResult('', '', 0)

    with pytest.raises(RuntimeError, match='network-backed filesystem'):
        manager._preflight_mountability('/mnt/network/image.img')


@pytest.mark.mock
def test_preflight_rejects_when_losetup_probe_fails():
    """Losetup probe failures should raise actionable runtime errors."""
    manager = ImageFileManager.__new__(ImageFileManager)

    manager._is_network_mounted_path = lambda path: False
    manager._run_local = lambda command, sudo=False: CommandResult('', 'losetup failed', 1)

    with pytest.raises(RuntimeError, match='Mountability probe failed'):
        manager._preflight_mountability('/tmp/image.img')


@pytest.mark.mock
def test_preflight_detaches_probe_loop_device_on_success():
    """Successful probes should detach temporary loop device."""
    manager = ImageFileManager.__new__(ImageFileManager)

    manager._is_network_mounted_path = lambda path: False
    commands: list[tuple[str, bool]] = []

    def fake_run_local(command: str, sudo: bool = False) -> CommandResult:
        commands.append((command, sudo))
        if command.startswith('losetup -f --show --read-only'):
            return CommandResult('/dev/loop7\n', '', 0)
        if command == 'losetup -d /dev/loop7':
            return CommandResult('', '', 0)
        return CommandResult('', '', 1)

    manager._run_local = fake_run_local

    manager._preflight_mountability('/tmp/image.img')

    assert commands == [
        ('losetup -f --show --read-only /tmp/image.img', True),
        ('losetup -d /dev/loop7', True),
    ]
