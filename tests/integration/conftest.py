"""Integration test shared fixtures and utilities."""
import pytest
import os
import subprocess
import tempfile
import shutil


def _unmountScopedTree(rootPath: str) -> None:
    """Unmount only mount points under rootPath (deepest first)."""
    realRootPath = os.path.realpath(rootPath)
    if not realRootPath.startswith("/tmp/pytest_mount_"):
        return

    mountTargets = []
    with open("/proc/self/mounts", "r", encoding="utf-8") as mountsFile:
        for mountLine in mountsFile:
            fields = mountLine.split()
            if len(fields) < 2:
                continue
            mountPoint = fields[1]
            if mountPoint == realRootPath or mountPoint.startswith(realRootPath + "/"):
                mountTargets.append(mountPoint)

    for mountPoint in sorted(set(mountTargets), key=len, reverse=True):
        try:
            subprocess.run(["sudo", "umount", mountPoint], stderr=subprocess.DEVNULL, timeout=5, check=False)
        except Exception:
            pass


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
        text=True
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
    yield tempDir
    # Cleanup - try to unmount anything stuck, then remove directory
    _unmountScopedTree(tempDir)
    try:
        shutil.rmtree(tempDir, ignore_errors=True)
    except Exception:
        pass


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
def cleanupMounts(request, keepMounted):
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
