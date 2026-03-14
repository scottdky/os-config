"""Integration test shared fixtures and utilities."""
import pytest
import os
import subprocess
import tempfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UNMOUNT_SCRIPT = str(PROJECT_ROOT / "os" / "unmnt_image.sh")
OWNERSHIP_MARKER_NAME = ".os_config_test_owned_mount"

def _unmountScopedTree(rootPath: str) -> None:
    """Unmount only mount points under rootPath using shared unmount script."""
    realRootPath = os.path.realpath(rootPath)
    if not realRootPath.startswith("/tmp/pytest_mount_"):
        return

    if not os.path.exists(UNMOUNT_SCRIPT):
        return

    markerPath = os.path.join(realRootPath, OWNERSHIP_MARKER_NAME)
    isTestOwned = os.path.exists(markerPath)

    subprocess.run(
        ["bash", UNMOUNT_SCRIPT, realRootPath],
        capture_output=True,
        text=True,
        check=False,
    )

    if not _is_mount_active(realRootPath):
        return

    if not isTestOwned:
        print(
            f"Warning: Refusing force cleanup for non-owned mount path: {realRootPath}. "
            "Resolve manually if still mounted."
        )
        return

    subprocess.run(
        ["bash", UNMOUNT_SCRIPT, realRootPath, "force"],
        capture_output=True,
        text=True,
        check=False,
    )


def _is_mount_active(targetPath: str) -> bool:
    """Return True when targetPath is currently mounted."""
    result = subprocess.run(
        ["findmnt", "-T", targetPath],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture(scope="session")
def checkSudo():
    """Ensure privileged commands can run via sudo."""
    result = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode != 0:
        pytest.skip("Integration tests require sudo access. Run: sudo -v, then rerun tests.")


@pytest.fixture(scope="session")
def checkQemu():
    """Ensure qemu-arm-static is available."""
    result = subprocess.run(
        ["which", "qemu-arm-static"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "qemu-arm-static not found. Install with:\n"
            "  sudo apt-get install qemu-user-static"
        )


@pytest.fixture
def tempMountDir():
    """Create a temporary directory for mounting, cleanup after test."""
    tempDir = tempfile.mkdtemp(prefix="pytest_mount_")

    markerPath = os.path.join(tempDir, OWNERSHIP_MARKER_NAME)
    with open(markerPath, "w", encoding="utf-8") as markerFile:
        markerFile.write("owned-by-os-config-integration-tests\n")

    yield tempDir
    # Cleanup - try to unmount anything stuck, then remove directory
    _unmountScopedTree(tempDir)
    try:
        shutil.rmtree(tempDir, ignore_errors=True)
    except OSError:
        pass


@pytest.fixture
def isMountActive():
    """Expose mount-active checks to integration tests."""

    def _check(path: str) -> bool:
        return _is_mount_active(path)

    return _check


@pytest.fixture(scope="session")
def testImagePath():
    """Return path to test Raspberry Pi image (or None if not present).

    Integration tests will skip if no test image is available.
    Run tests/integration/setup_test_env.sh to download/create one.
    """
    fixturesDir = os.path.join(os.path.dirname(__file__), "fixtures")
    possibleImages = [
        os.path.join(fixturesDir, "raspios-lite-test.img"),
        os.path.join(fixturesDir, "test-image.img"),
    ]

    for imgPath in possibleImages:
        if os.path.exists(imgPath):
            return imgPath

    return None


@pytest.fixture
def cleanupMounts(keepMounted):
    """Cleanup any mounts after test (unless --keep-mounted flag set)."""
    mountedPaths = []

    def registerMount(path):
        """Register a mount path for cleanup."""
        mountedPaths.append(path)

    yield registerMount

    # Cleanup after test
    if not keepMounted:
        for path in mountedPaths:
            _unmountScopedTree(path)


@pytest.fixture
def loopDeviceFromImage(checkSudo):
    """Attach loop devices from images and detach them automatically on teardown."""
    _ = checkSudo
    attachedDevices: list[str] = []

    def _attach(imagePath: str) -> str:
        result = subprocess.run(
            ["sudo", "losetup", "-f", "--show", "-P", imagePath],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or "unknown losetup error"
            if 'permission denied' in stderr.lower() or 'operation not permitted' in stderr.lower():
                pytest.skip(
                    "Loop device attach is not permitted in this environment. "
                    "Run on a host with loop-device privileges."
                )
            raise RuntimeError(f"Failed to attach loop device for {imagePath}: {stderr}")
        loopDev = result.stdout.strip()
        if not loopDev:
            raise RuntimeError(f"Failed to parse loop device output for {imagePath}")
        attachedDevices.append(loopDev)
        return loopDev

    yield _attach

    for loopDev in reversed(attachedDevices):
        subprocess.run(["sudo", "losetup", "-d", loopDev], check=False)
