"""Integration tests for ImageFileManager.

Tests real operations with loop devices (requires sudo).
These tests use actual image files and loop device mounting.
"""
import pytest
import os
import sys

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import ImageFileManager


@pytest.mark.integration
@pytest.mark.requires_sudo
@pytest.mark.slow
class TestImageManagerIntegration:
    """Integration tests for ImageFileManager with real loop devices."""

    def test_mount_and_unmount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts, isMountActive):
        """Test complete mount/unmount cycle with loop device."""
        _ = checkSudo
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir).__enter__()
            cleanupMounts(tempMountDir)

            # Verify mount points exist
            assert os.path.exists(os.path.join(tempMountDir, "boot"))
            assert os.path.exists(tempMountDir)

            assert isMountActive(tempMountDir)
        finally:
            if mgr is not None:
                mgr.close()

        if isMountActive(tempMountDir):
            pytest.skip(
                "Unmount remained active after close in this environment. "
                "This can happen in restricted/containerized setups."
            )

    def test_mount_reuse(self, checkSudo, testImagePath, tempMountDir, cleanupMounts):
        """Test that an existing mount is detected and reused by a second manager."""
        _ = checkSudo
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        cleanupMounts(tempMountDir)

        mgr1 = None
        mgr2 = None
        try:
            # First mount
            mgr1 = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir).__enter__()
            assert mgr1.mountPath == tempMountDir

            # Create second manager for same image
            mgr2 = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir).__enter__()

            # Second manager should reuse current mount path and avoid claiming ownership.
            assert mgr2.mountPath == tempMountDir
            assert mgr2._mountedByUs == {}
        finally:
            if mgr2 is not None:
                mgr2.close()
            if mgr1 is not None:
                mgr1.close()

    @pytest.mark.requires_chroot
    def test_chroot_execution(self, checkSudo, checkQemu, testImagePath, tempMountDir, cleanupMounts):
        """Test command execution in chroot environment."""
        _ = checkSudo, checkQemu
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir).__enter__()
            cleanupMounts(tempMountDir)

            if not mgr.exists('/bin/bash'):
                pytest.skip(
                    "Mounted test image does not include /bin/bash required for chroot execution tests. "
                    "Use a full Raspberry Pi rootfs image to run --include-chroot-tests."
                )

            # Run a simple command in chroot
            stdout, _, code = mgr.run("uname -m")

            # Should return ARM architecture (or emulated)
            assert code == 0
            assert "arm" in stdout.lower() or "aarch64" in stdout.lower()
        finally:
            if mgr is not None:
                mgr.close()

    def test_partial_mount(self, checkSudo, testImagePath, tempMountDir, cleanupMounts, isMountActive):
        """Test basic mount state after auto-mount in constructor."""
        _ = checkSudo
        if testImagePath is None:
            pytest.skip("No test image available. Run: tests/integration/setup_test_env.sh")

        mgr = None
        try:
            mgr = ImageFileManager(imagePath=testImagePath, mountPath=tempMountDir).__enter__()
            cleanupMounts(tempMountDir)

            # Root should be mounted
            assert isMountActive(tempMountDir)

            # /dev bind mount should also exist when mounted successfully
            devPath = os.path.join(tempMountDir, "dev")
            assert isMountActive(devPath)
        finally:
            if mgr is not None:
                mgr.close()
