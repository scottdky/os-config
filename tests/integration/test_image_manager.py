"""Integration tests for ImageFileManager.

Tests real operations with loop devices (requires sudo).
These tests use actual image files and loop device mounting.
"""
import pytest
import os
import sys
import subprocess
import tempfile

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import ImageFileManager


@pytest.mark.integration
@pytest.mark.requires_sudo
@pytest.mark.slow
class TestImageManagerIntegration:
    """Integration tests for ImageFileManager with real loop devices."""

    def test_mount_and_unmount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts):
        """Test complete mount/unmount cycle with loop device."""
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir)
            cleanupMounts(tempMountDir)

            # Verify mount points exist
            assert os.path.exists(os.path.join(tempMountDir, "boot"))
            assert os.path.exists(tempMountDir)

            # Check /proc/mounts to verify actual mounts
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                assert tempMountDir in mounts
        finally:
            if mgr is not None:
                mgr.close()

        # Verify unmounted (may still have directory but no mount)
        with open("/proc/mounts", "r") as f:
            mounts = f.read()
            assert tempMountDir not in mounts

    def test_mount_reuse(self, checkSudo, testImagePath, tempMountDir, cleanupMounts):
        """Test that existing loop mount is detected and reused."""
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        cleanupMounts(tempMountDir)

        mgr1 = None
        mgr2 = None
        try:
            # First mount
            mgr1 = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir)

            # Get loop device from first mount
            losetupOutput = subprocess.run(
                ["sudo", "losetup", "-j", testImagePath],
                capture_output=True,
                text=True
            )
            firstLoopDev = losetupOutput.stdout.split(":")[0] if losetupOutput.stdout else None

            # Create second manager for same image
            mgr2 = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir)

            # Should detect existing mount
            existingMount = mgr2._find_existing_loop_mount()
            assert existingMount is not None
            assert existingMount == tempMountDir

            # Should reuse same loop device
            assert firstLoopDev is not None
        finally:
            if mgr2 is not None:
                mgr2.close()
            if mgr1 is not None:
                mgr1.close()

    @pytest.mark.requires_chroot
    def test_chroot_execution(self, checkSudo, checkQemu, testImagePath, tempMountDir, cleanupMounts):
        """Test command execution in chroot environment."""
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir)
            cleanupMounts(tempMountDir)

            # Run a simple command in chroot
            stdout, stderr, code = mgr.run("uname -m")

            # Should return ARM architecture (or emulated)
            assert code == 0
            assert "arm" in stdout.lower() or "aarch64" in stdout.lower()
        finally:
            if mgr is not None:
                mgr.close()

    def test_partial_mount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts):
        """Test basic mount state after auto-mount in constructor."""
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir)
            cleanupMounts(tempMountDir)

            # Root should be mounted
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                assert tempMountDir in mounts

            # /dev bind mount should also exist when mounted successfully
            devPath = os.path.join(tempMountDir, "dev")
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                assert devPath in mounts
        finally:
            if mgr is not None:
                mgr.close()
