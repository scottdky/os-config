"""Mock tests for interactive menu back/exit behavior."""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import factory as cmd_manager
from lib.managers import SDCardManager


class _FakeTerminalMenu:
    """Simple terminal menu stub returning pre-seeded selections."""

    _responses: list[int | None] = []

    def __init__(self, options, title=None):
        self.options = options
        self.title = title

    def show(self):
        if not _FakeTerminalMenu._responses:
            return None
        return _FakeTerminalMenu._responses.pop(0)


@pytest.mark.mock
class TestInteractiveMenuFlow:
    """Validate abort/exit flow in interactive menus."""

    def test_sdcard_abort_option_returns_none(self):
        """Choosing explicit abort in SD card picker should return None."""
        devices = [{
            'device': '/dev/sdb',
            'size': '16G',
            'vendor': 'Vendor',
            'model': 'Model',
            'mounted': False,
            'mountpoints': []
        }]

        with mock.patch.object(SDCardManager, 'detect_usb_devices', return_value=devices), \
             mock.patch('simple_term_menu.TerminalMenu', _FakeTerminalMenu):
            _FakeTerminalMenu._responses = [1]  # index 1 = "Abort (back to main menu)"
            manager = SDCardManager.from_interactive_selection()

        assert manager is None

    def test_main_menu_exit_option_returns_none(self):
        """Choosing Exit in main menu should return None without errors."""
        with mock.patch('simple_term_menu.TerminalMenu', _FakeTerminalMenu):
            _FakeTerminalMenu._responses = [4]  # index 4 = "Exit"
            manager = cmd_manager.interactive_create_manager()

        assert manager is None
