"""Mock tests for loop device detection.

Tests ImageFileManager._find_existing_loop_mount() with mocked
losetup and /proc/mounts output.
"""
import pytest
from unittest import mock
import sys
import os
import stat

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import ImageFileManager


@pytest.mark.mock
class TestLoopDetection:
    """Test loop device detection with mocked system output."""

    @staticmethod
    def _mock_regular_file_stat() -> mock.Mock:
        """Return a stat-like object for a regular file."""
        result = mock.Mock()
        result.st_mode = stat.S_IFREG
        return result

    def test_loop_device_found(self):
        """Detect existing loop device for image file."""
        imagePath = "/home/user/test.img"

        # Mock losetup -j output
        mockLosetup = "/dev/loop0: []: (/home/user/test.img)\n"

        # Mock /proc/mounts showing loop0 mounted
        mockMounts = (
            "/dev/loop0p1 /tmp/test/boot vfat rw 0 0\n"
            "/dev/loop0p2 /tmp/test ext4 rw 0 0\n"
        )

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
             mock.patch('lib.managers.image.os.path.isfile', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_regular_file_stat()), \
             mock.patch('builtins.open', mock.mock_open(read_data=mockMounts)), \
             mock.patch.object(ImageFileManager, '_perform_mount'):

            # losetup -j call
            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockLosetup
            )

            mgr = ImageFileManager(imagePath=imagePath, mountPath="/tmp/test")
            mountPath = mgr._find_existing_loop_mount()

            assert mountPath == "/tmp/test"

    def test_no_loop_device(self):
        """No existing loop device for image file."""
        imagePath = "/home/user/test.img"

        # Mock empty losetup -j output
        mockLosetup = ""

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
             mock.patch('lib.managers.image.os.path.isfile', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_regular_file_stat()), \
             mock.patch.object(ImageFileManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockLosetup
            )

            mgr = ImageFileManager(imagePath=imagePath, mountPath="/tmp/test")
            result = mgr._find_existing_loop_mount()

            assert result is None

    def test_loop_but_not_mounted(self):
        """Loop device exists but partitions not mounted."""
        imagePath = "/home/user/test.img"

        # Mock losetup -j output
        mockLosetup = "/dev/loop0: []: (/home/user/test.img)\n"

        # Mock /proc/mounts with no loop0 entries
        mockMounts = (
            "/dev/sda1 / ext4 rw 0 0\n"
            "/dev/sda2 /home ext4 rw 0 0\n"
        )

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
             mock.patch('lib.managers.image.os.path.isfile', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_regular_file_stat()), \
             mock.patch('builtins.open', mock.mock_open(read_data=mockMounts)), \
             mock.patch.object(ImageFileManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockLosetup
            )

            mgr = ImageFileManager(imagePath=imagePath, mountPath="/tmp/test")
            result = mgr._find_existing_loop_mount()

            # Loop exists but not mounted - return None to force new mount
            assert result is None

    def test_multiple_loop_devices(self):
        """Multiple loop devices, only one matches our image."""
        imagePath = "/home/user/test.img"

        # Mock losetup -j output - should only show our image
        mockLosetup = "/dev/loop0: []: (/home/user/test.img)\n"

        # Mock /proc/mounts with multiple loop devices
        mockMounts = (
            "/dev/loop0p1 /tmp/test/boot vfat rw 0 0\n"
            "/dev/loop0p2 /tmp/test ext4 rw 0 0\n"
            "/dev/loop1p1 /other/mount vfat rw 0 0\n"
        )

        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
             mock.patch('lib.managers.image.os.path.isfile', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_regular_file_stat()), \
             mock.patch('builtins.open', mock.mock_open(read_data=mockMounts)), \
             mock.patch.object(ImageFileManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockLosetup
            )

            mgr = ImageFileManager(imagePath=imagePath, mountPath="/tmp/test")
            mountPath = mgr._find_existing_loop_mount()

            # Should find root mount path for loop0
            assert mountPath == "/tmp/test"

    def test_different_mount_path(self):
        """Loop exists at different mount path than requested."""
        imagePath = "/home/user/test.img"

        mockLosetup = "/dev/loop0: []: (/home/user/test.img)\n"

        # Mounted at /mnt/old instead of /tmp/test
        mockMounts = (
            "/dev/loop0p1 /mnt/old/boot vfat rw 0 0\n"
            "/dev/loop0p2 /mnt/old ext4 rw 0 0\n"
        )

        # Request mount at /tmp/test
        with mock.patch('lib.managers.image.subprocess.run') as mockRun, \
             mock.patch('lib.managers.image.os.path.exists', return_value=True), \
             mock.patch('lib.managers.image.os.path.isfile', return_value=True), \
               mock.patch('lib.managers.image.os.stat', return_value=self._mock_regular_file_stat()), \
             mock.patch('builtins.open', mock.mock_open(read_data=mockMounts)), \
             mock.patch.object(ImageFileManager, '_perform_mount'):

            mockRun.return_value = mock.Mock(
                returncode=0,
                stdout=mockLosetup
            )

            mgr = ImageFileManager(imagePath=imagePath, mountPath="/tmp/test")
            mountPath = mgr._find_existing_loop_mount()

            # Should find root mount path even if it's different than requested
            assert mountPath == "/mnt/old"
