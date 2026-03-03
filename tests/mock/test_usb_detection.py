"""Mock tests for USB device detection.

Tests detect_usb_devices() with mocked lsblk output covering:
- Single USB device
- Multiple USB devices
- No USB devices
- Mixed removable/non-removable devices
"""
import pytest
from unittest import mock
import sys
import os
import json

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.cmd_manager import SDCardManager


@pytest.mark.mock
class TestUsbDetection:
    """Test USB device detection with mocked lsblk output."""

    def test_single_usb_device(self):
        """Detect single USB device."""
        mockOutput = json.dumps({
            "blockdevices": [
                {
                    "name": "sda",
                    "size": "931.5G",
                    "type": "disk",
                    "tran": "sata",
                    "rm": False,
                    "mountpoint": None
                },
                {
                    "name": "sdb",
                    "size": "28.9G",
                    "type": "disk",
                    "tran": "usb",
                    "rm": True,
                    "mountpoint": None
                }
            ]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 1
            assert devices[0]["device"] == "/dev/sdb"
            assert devices[0]["size"] == "28.9G"

    def test_multiple_usb_devices(self):
        """Detect multiple USB devices."""
        mockOutput = json.dumps({
            "blockdevices": [
                {
                    "name": "sdb",
                    "size": "28.9G",
                    "type": "disk",
                    "tran": "usb",
                    "rm": True,
                    "mountpoint": None
                },
                {
                    "name": "sdc",
                    "size": "16G",
                    "type": "disk",
                    "tran": "usb",
                    "rm": True,
                    "mountpoint": None
                }
            ]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 2
            assert devices[0]["device"] == "/dev/sdb"
            assert devices[1]["device"] == "/dev/sdc"

    def test_no_usb_devices(self):
        """No USB devices detected."""
        mockOutput = json.dumps({
            "blockdevices": [
                {
                    "name": "sda",
                    "size": "931.5G",
                    "type": "disk",
                    "tran": "sata",
                    "rm": False,
                    "mountpoint": None
                }
            ]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 0

    def test_rm_field_variations(self):
        """Test different values for 'rm' field (boolean vs string).

        Regression test for USB detection bug where lsblk returns
        boolean True but code compared to string '1'.
        """
        # Test with boolean True
        mockOutput1 = json.dumps({
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
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput1)
            devices = SDCardManager.detect_usb_devices()
            assert len(devices) == 1

        # Test with string "1"
        mockOutput2 = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "size": "16G",
                "type": "disk",
                "tran": "usb",
                "rm": "1",
                "mountpoint": None
            }]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput2)
            devices = SDCardManager.detect_usb_devices()
            assert len(devices) == 1

        # Test with integer 1
        mockOutput3 = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "size": "16G",
                "type": "disk",
                "tran": "usb",
                "rm": 1,
                "mountpoint": None
            }]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(returncode=0, stdout=mockOutput3)
            devices = SDCardManager.detect_usb_devices()
            assert len(devices) == 1

    def test_mmc_device_detection(self):
        """Detect MMC/SD card devices (mmcblk)."""
        mockOutput = json.dumps({
            "blockdevices": [
                {
                    "name": "mmcblk0",
                    "size": "29.7G",
                    "type": "disk",
                    "tran": "usb",
                    "rm": True,
                    "mountpoint": None
                }
            ]
        })

        with mock.patch('lib.cmd_manager.subprocess.run') as mockRun:
            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            devices = SDCardManager.detect_usb_devices()

            assert len(devices) == 1
            assert devices[0]["device"] == "/dev/mmcblk0"
            assert devices[0]["size"] == "29.7G"
