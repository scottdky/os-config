"""Unit tests for USB device detection logic (classmethod).

Tests SDCardManager.detect_usb_devices() with mocked lsblk output.
This is a pure classmethod test that doesn't require instantiation.
"""
import pytest
from unittest import mock
import sys
import os
import json

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.cmd_manager import SDCardManager


@pytest.mark.unit
class TestUsbDetectionClassmethod:
    """Test USB device detection classmethod (no instance needed)."""

    def test_classmethod_doesnt_require_instance(self):
        """Verify detect_usb_devices can be called without instance."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "size": "16G",
                "type": "disk",
                "tran": "usb",
                "rm": True,
                "mountpoint": None
            }]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput)

            # Call as classmethod - no instance needed
            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 1
            assert devices[0]["device"] == "/dev/sdb"

    def test_returns_list_of_dicts(self):
        """Verify return type is list of dictionaries."""
        mockOutput = json.dumps({"blockdevices": []})

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput)

            devices = SDCardManager.detect_usb_devices()

            assert isinstance(devices, list)

    def test_each_device_has_required_fields(self):
        """Verify each detected device has device and size fields."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdc",
                "size": "32G",
                "type": "disk",
                "tran": "usb",
                "rm": True,
                "mountpoint": None
            }]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput)

            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 1
            assert "device" in devices[0]
            assert "size" in devices[0]
            assert devices[0]["device"] == "/dev/sdc"
            assert devices[0]["size"] == "32G"
