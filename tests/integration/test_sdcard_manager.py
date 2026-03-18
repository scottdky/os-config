"""Integration tests for SDCardManager.

By default, integration runs only safe loopback tests. Real-device tests are
enabled only when --use-real-device is provided.
"""
import json
import pytest
import os
import subprocess
import sys

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import SDCardManager


def _read_partitions_for_device(devicePath: str) -> dict[str, str]:
    """Read root/boot partition paths from lsblk JSON for a device."""
    result = subprocess.run(
        ["lsblk", "--json", "-o", "NAME,FSTYPE", devicePath],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    partitions: dict[str, str] = {}
    blockDevices = data.get("blockdevices") or []
    if not blockDevices:
        return partitions

    children = blockDevices[0].get("children") or []
    for partition in children:
        partName = partition.get("name")
        fsType = partition.get("fstype")
        if not partName:
            continue
        partPath = f"/dev/{partName}"
        if fsType == "ext4" and "root" not in partitions:
            partitions["root"] = partPath
        if fsType in {"vfat", "fat16", "fat32"} and "boot" not in partitions:
            partitions["boot"] = partPath

    return partitions


@pytest.mark.integration
@pytest.mark.requires_sudo
@pytest.mark.slow
class TestSDCardManagerIntegration:
    """Integration tests for SDCardManager."""

    def test_loopback_mount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts, loopDeviceFromImage, isMountActive):
        """Test SD card manager with loopback device (safe for CI)."""
        _ = checkSudo
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        loopDev = loopDeviceFromImage(testImagePath)
        cleanupMounts(tempMountDir)

        mgr = None
        try:
            mgr = SDCardManager(devicePath=loopDev, mountPath=tempMountDir).__enter__()

            # Detect partitions via lsblk
            partitions = _read_partitions_for_device(loopDev)
            assert "root" in partitions

            # Verify mounted
            assert isMountActive(tempMountDir)

            # Unmount
            mgr.close()

        finally:
            if mgr is not None:
                mgr.close()

    def test_partition_detection(self, checkSudo, testImagePath, tempMountDir, loopDeviceFromImage):
        """Test partition detection on loopback device."""
        _ = checkSudo
        if testImagePath is None:
            pytest.skip("No test image available")

        loopDev = loopDeviceFromImage(testImagePath)

        mgr = None
        try:
            mgr = SDCardManager(devicePath=loopDev, mountPath=tempMountDir).__enter__()

            partitions = _read_partitions_for_device(loopDev)

            # Should detect at least root partition
            assert "root" in partitions
            assert partitions["root"].startswith(loopDev)

            # Typical Raspberry Pi images have boot partition
            if "boot" in partitions:
                assert partitions["boot"].startswith(loopDev)

        finally:
            if mgr is not None:
                mgr.close()


@pytest.mark.integration
@pytest.mark.requires_device
@pytest.mark.slow
class TestRealSDCard:
    """Tests requiring real SD card (--use-real-device [auto] or explicit path)."""

    def test_real_device_detection(self, checkSudo, realDevice, tempMountDir, cleanupMounts):
        """Test partition detection and mounting with real SD card."""
        _ = checkSudo
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
            mgr = SDCardManager(devicePath=realDevice, mountPath=tempMountDir).__enter__()

            # Detect partitions
            partitions = _read_partitions_for_device(realDevice)
            assert "root" in partitions

            # Verify mounted
            assert os.path.exists(tempMountDir)
            with open("/proc/mounts", "r", encoding="utf-8") as f:
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
        _ = checkSudo
        if realDevice is None:
            pytest.skip("No real device specified. Use: --use-real-device or --use-real-device=/dev/sdX")

        mgr = None
        try:
            mgr = SDCardManager(devicePath=realDevice, mountPath=tempMountDir).__enter__()
            partitions = _read_partitions_for_device(realDevice)
            assert "root" in partitions
            assert partitions["root"].startswith(realDevice)
        finally:
            if mgr is not None:
                mgr.close()
