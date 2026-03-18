"""Mock tests for partition detection logic.

Tests SDCardManager._detect_partitions() with mocked lsblk output
for various partition layouts and filesystem types.
"""
import pytest
from unittest import mock
import sys
import os
import json
import stat

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import SDCardManager


@pytest.mark.mock
class TestPartitionDetection:
    """Test partition detection with mocked lsblk output."""

    @staticmethod
    def _mock_block_device_stat() -> mock.Mock:
        """Return a stat-like object for a block device."""
        result = mock.Mock()
        result.st_mode = stat.S_IFBLK
        return result

    def test_typical_raspberry_pi_layout(self):
        """Detect typical Raspberry Pi partition layout (FAT boot + ext4 root)."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "children": [
                    {
                        "name": "sdb1",
                        "fstype": "vfat",
                        "size": "512M"
                    },
                    {
                        "name": "sdb2",
                        "fstype": "ext4",
                        "size": "28G"
                    }
                ]
            }]
        })

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_block_device_stat()), \
             mock.patch('lib.managers.image.os.path.isdir', return_value=False), \
             mock.patch.object(SDCardManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            with SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test") as mgr:
                partitions = mgr._detect_partitions()

                assert partitions["boot"] == "/dev/sdb1"
                assert partitions["root"] == "/dev/sdb2"

    def test_mmc_partition_layout(self):
        """Detect MMC device with p-style partition naming."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "mmcblk0",
                "children": [
                    {
                        "name": "mmcblk0p1",
                        "fstype": "vfat",
                        "size": "256M"
                    },
                    {
                        "name": "mmcblk0p2",
                        "fstype": "ext4",
                        "size": "29G"
                    }
                ]
            }]
        })

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_block_device_stat()), \
             mock.patch('lib.managers.image.os.path.isdir', return_value=False), \
             mock.patch.object(SDCardManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            with SDCardManager(devicePath="/dev/mmcblk0", mountPath="/tmp/test") as mgr:
                partitions = mgr._detect_partitions()

                assert partitions["boot"] == "/dev/mmcblk0p1"
                assert partitions["root"] == "/dev/mmcblk0p2"

    def test_single_partition(self):
        """Handle device with only one partition."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "children": [
                    {
                        "name": "sdb1",
                        "fstype": "ext4",
                        "size": "29G"
                    }
                ]
            }]
        })

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_block_device_stat()), \
             mock.patch('lib.managers.image.os.path.isdir', return_value=False), \
             mock.patch.object(SDCardManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            with SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test") as mgr:
                partitions = mgr._detect_partitions()

                # Only root partition exists
                assert partitions.get("boot") is None
                assert partitions["root"] == "/dev/sdb1"

    def test_no_partitions(self):
        """Handle device with no partitions."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "children": []
            }]
        })

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_block_device_stat()), \
             mock.patch('lib.managers.image.os.path.isdir', return_value=False), \
             mock.patch.object(SDCardManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            with SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test") as mgr:
                partitions = mgr._detect_partitions()

                # Empty dict
                assert len(partitions) == 0

    def test_multiple_ext4_partitions(self):
        """When multiple ext4 partitions exist, use the largest as root."""
        mockOutput = json.dumps({
            "blockdevices": [{
                "name": "sdb",
                "children": [
                    {
                        "name": "sdb1",
                        "fstype": "vfat",
                        "size": "512M"
                    },
                    {
                        "name": "sdb2",
                        "fstype": "ext4",
                        "size": "2G"
                    },
                    {
                        "name": "sdb3",
                        "fstype": "ext4",
                        "size": "26G"
                    }
                ]
            }]
        })

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_block_device_stat()), \
             mock.patch('lib.managers.image.os.path.isdir', return_value=False), \
             mock.patch.object(SDCardManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockOutput
            )

            with SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test") as mgr:
                partitions = mgr._detect_partitions()

                assert partitions["boot"] == "/dev/sdb1"
                # Should pick largest ext4 partition
                assert partitions["root"] == "/dev/sdb3"
