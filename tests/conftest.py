"""Shared pytest fixtures for all test types."""
import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def projectRoot():
    """Return the absolute path to the project root."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--keep-mounted",
        action="store_true",
        default=False,
        help="Keep filesystems mounted after integration tests (for debugging)"
    )
    parser.addoption(
        "--use-real-device",
        action="store",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "Enable real-device integration tests. "
            "Use --use-real-device for auto-detect (single removable USB device required), "
            "or --use-real-device=/dev/sdX for explicit device path."
        )
    )
    parser.addoption(
        "--include-chroot-tests",
        action="store_true",
        default=False,
        help="Include integration tests marked requires_chroot"
    )


def pytest_collection_modifyitems(config, items):
    """Skip high-risk integration subsets unless explicitly enabled."""
    realDeviceOpt = config.getoption("--use-real-device")
    includeChrootTests = config.getoption("--include-chroot-tests")

    skipRealDevice = pytest.mark.skip(
        reason="Real-device tests disabled by default. Use --use-real-device to enable."
    )
    skipChroot = pytest.mark.skip(
        reason="Chroot tests disabled by default. Use --include-chroot-tests to enable."
    )

    for item in items:
        if "requires_device" in item.keywords and realDeviceOpt is None:
            item.add_marker(skipRealDevice)
        if "requires_chroot" in item.keywords and not includeChrootTests:
            item.add_marker(skipChroot)


@pytest.fixture
def keepMounted(request):
    """Return True if --keep-mounted flag was passed."""
    return request.config.getoption("--keep-mounted")


@pytest.fixture
def realDevice(request):
    """Resolve real device path from --use-real-device option."""
    realDeviceOpt = request.config.getoption("--use-real-device")
    if realDeviceOpt is None:
        return None

    from lib.cmd_manager import SDCardManager

    devices = SDCardManager.detect_usb_devices()

    if realDeviceOpt == "auto":
        if len(devices) == 1:
            return devices[0]["device"]
        availableDevices = [d.get("device", "unknown") for d in devices]
        raise pytest.UsageError(
            "--use-real-device (auto) requires exactly one removable USB device. "
            f"Detected: {availableDevices}"
        )

    # Explicit device path mode
    matchingDevices = [d for d in devices if d.get("device") == realDeviceOpt]
    if not matchingDevices:
        availableDevices = [d.get("device", "unknown") for d in devices]
        raise pytest.UsageError(
            f"Requested device {realDeviceOpt} was not detected as removable USB device. "
            f"Detected: {availableDevices}"
        )
    return realDeviceOpt
