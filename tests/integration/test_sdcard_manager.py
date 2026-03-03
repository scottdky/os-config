"""Integration tests for SDCardManager.

By default, integration runs only safe loopback tests. Real-device tests are
enabled only when --use-real-device is provided.
"""
import pytest
import os
import sys
import subprocess

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.cmd_manager import SDCardManager


@pytest.mark.integration
@pytest.mark.requires_sudo
@pytest.mark.slow
class TestSDCardManagerIntegration:
    """Integration tests for SDCardManager."""

    def test_loopback_mount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts):
        """Test SD card manager with loopback device (safe for CI)."""
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        # Create loop device from test image
        result = subprocess.run(
            ["sudo", "losetup", "-f", "--show", "-P", testImagePath],
            capture_output=True,
            text=True,
            check=True
        )
        loopDev = result.stdout.strip()
        cleanupMounts(tempMountDir)

        try:
            # Test SDCardManager with loop device
            mgr = SDCardManager(devicePath=loopDev, mountPath=tempMountDir)

            # Detect partitions
            partitions = mgr._detect_partitions()
            assert "root" in partitions

            # Auto-mounted in constructor

            # Verify mounted
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                assert tempMountDir in mounts

            # Unmount
            mgr.close()

        finally:
            # Cleanup loop device
            subprocess.run(["sudo", "losetup", "-d", loopDev], check=False)

    def test_partition_detection(self, checkSudo, testImagePath, tempMountDir):
        """Test partition detection on loopback device."""
        if testImagePath is None:
            pytest.skip("No test image available")

        # Create loop device
        result = subprocess.run(
            ["sudo", "losetup", "-f", "--show", "-P", testImagePath],
            capture_output=True,
            text=True,
            check=True
        )
        loopDev = result.stdout.strip()

        mgr = None
        try:
            mgr = SDCardManager(devicePath=loopDev, mountPath=tempMountDir)

            partitions = mgr._detect_partitions()

            # Should detect at least root partition
            assert "root" in partitions
            assert partitions["root"].startswith(loopDev)

            # Typical Raspberry Pi images have boot partition
            if "boot" in partitions:
                assert partitions["boot"].startswith(loopDev)

        finally:
            if mgr is not None:
                mgr.close()
            subprocess.run(["sudo", "losetup", "-d", loopDev], check=False)


@pytest.mark.integration
@pytest.mark.requires_device
@pytest.mark.slow
class TestRealSDCard:
    """Tests requiring real SD card (--use-real-device [auto] or explicit path)."""

    def test_real_device_detection(self, checkSudo, realDevice, tempMountDir, cleanupMounts):
        """Test partition detection and mounting with real SD card."""
        if realDevice is None:
            pytest.skip("No real device specified. Use: --use-real-device or --use-real-device=/dev/sdX")

        # Safety check: verify device is removable
        allDevices = SDCardManager.detect_usb_devices()
        matchingDevices = [d for d in allDevices if d["device"] == realDevice]

        if not matchingDevices:
            pytest.fail(
                f"Device {realDevice} not found or not removable. "
                f"Available USB devices: {[d['device'] for d in allDevices]}"
            )

        if len(allDevices) > 1:
            pytest.fail(
                f"Multiple USB devices detected: {[d['device'] for d in allDevices]}. "
                "For safety, only one removable device should be connected during tests."
            )

        cleanupMounts(tempMountDir)

        mgr = None
        try:
            # Test with real device
            mgr = SDCardManager(devicePath=realDevice, mountPath=tempMountDir)

            # Detect partitions
            partitions = mgr._detect_partitions()
            assert "root" in partitions

            # Verify mounted
            assert os.path.exists(tempMountDir)
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                assert tempMountDir in mounts

            # Test command execution
            _, _, code = mgr.run("ls /")
            assert code == 0
        finally:
            if mgr is not None:
                mgr.close()

    def test_real_device_naming(self, checkSudo, realDevice, tempMountDir):
        """Test partition detection returns paths on real device."""
        if realDevice is None:
            pytest.skip("No real device specified. Use: --use-real-device or --use-real-device=/dev/sdX")

        mgr = None
        try:
            mgr = SDCardManager(devicePath=realDevice, mountPath=tempMountDir)
            partitions = mgr._detect_partitions()
            assert "root" in partitions
            assert partitions["root"].startswith(realDevice)
        finally:
            if mgr is not None:
                mgr.close()
