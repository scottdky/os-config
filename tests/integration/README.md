# Integration Tests

Comprehensive integration tests for ImageFileManager and SDCardManager using real system operations (loop devices, mounting, chroot).

## Prerequisites

- **Sudo access**: All integration tests require root privileges
- **qemu-user-static**: Required for ARM chroot execution
  ```bash
  sudo apt-get install qemu-user-static
  ```
- **Test image**: Download or create a Raspberry Pi test image

## Setup

Run the setup script to download/create a test image:

```bash
cd tests/integration
./setup_test_env.sh
```

Note: Run the setup script as your normal user (not with sudo). It will request sudo only for privileged steps when needed.

Choose option 1 (download full image) or option 2 (create minimal image).

## Running Tests

### All Integration Tests

```bash
cd tests/integration
./run_tests.py
```

This runs the safest integration subset by default (no real device and no chroot execution).

Interactive menu options in `run_tests.py`:
- Run safest integration tests (mount-only loopback)
- Run all non-device integration tests (includes chroot)
- Detect removable devices (no tests)
- Run real-device integration tests (requires device confirmation)

CLI mode examples:
```bash
cd tests/integration

# Safest subset (default in automated workflows)
./run_tests.py --mode safe

# Non-device full integration (includes chroot-marked tests)
./run_tests.py --mode non-device

# Detect devices only
./run_tests.py --mode detect

# Real-device mode with interactive device selection
./run_tests.py --mode device

# Real-device mode with explicit path
./run_tests.py --mode device --device /dev/sdb
```

Passing pytest arguments through `run_tests.py`:
```bash
# No "--" required; unknown args are forwarded to pytest
./run_tests.py --mode safe -k mount_and_unmount -vv --maxfail=1
./run_tests.py --mode non-device -k chroot_execution -vv
```

### Specific Test Files

```bash
cd tests/
../env/bin/python -m pytest -m integration tests/integration/test_image_manager.py
../env/bin/python -m pytest -m integration tests/integration/test_sdcard_manager.py

# Include chroot tests explicitly
../env/bin/python -m pytest -m integration --include-chroot-tests tests/integration/test_image_manager.py
```

### Keep Mounts for Debugging

```bash
cd tests/
../env/bin/python -m pytest -m integration --keep-mounted
```

Mounts will remain after tests for manual inspection.

### Test with Real SD Card

```bash
# IMPORTANT: Only connect ONE removable device for safety
cd tests/
../env/bin/python -m pytest -m integration --use-real-device

# Optional explicit device path
../env/bin/python -m pytest -m integration --use-real-device=/dev/sdb
```

Runner-based real-device flow (recommended):
```bash
cd tests/integration
./run_tests.py --mode device
```

Detection-only flow (no mounts, no tests):
```bash
cd tests/integration
./run_tests.py --mode detect
```

Safety checks:
- Verifies device is removable (via lsblk)
- Auto mode requires exactly one removable USB device
- Interactive script asks for explicit confirmation before running real-device tests

## Test Categories

### Safest default (`pytest -m integration`)
- image mount/unmount checks
- loopback SD mount/detection checks
- no real device tests
- no chroot command execution tests

### test_image_manager.py
- Loop device mounting/unmounting
- Mount reuse detection
- Chroot command execution
- Partial mounting (root only)

### test_sdcard_manager.py
- Partition detection (loopback)
- Mount/unmount cycles
- Real SD card detection (optional)
- Partition naming (mmcblk vs sdb style)

## Cleanup

If tests hang or leave mounts stuck:

```bash
cd tests/integration
sudo ./cleanup_all.sh
```

This will:
- Unmount all `/tmp/pytest_mount_*` directories
- Detach all loop devices for test images
- Clean up temporary directories

## Troubleshooting

### "No test image available"
Run `./setup_test_env.sh` to download/create a test image.

### Setup script permission issues
Run setup as your normal user (not `sudo ./setup_test_env.sh`).

### "Integration tests require sudo"
The test process should run as your normal user. Privileged operations run via `sudo` internally. Ensure sudo is available by running `sudo -v`.

### "All integration tests skipped"
Check these prerequisites:
- `sudo -v` succeeds
- `tests/integration/fixtures/raspios-lite-test.img` exists
- if running chroot tests: `qemu-arm-static` is installed and `--include-chroot-tests` is provided
- for chroot command tests: mounted image includes `/bin/bash` (full rootfs image, not partition-only/minimal fixtures)

### "Safe mode shows skips for loopback tests"
In restricted/containerized environments, `losetup` may be blocked even with sudo.
When that happens, loopback SD tests are skipped by design instead of failing.

To run those tests, use a host environment with loop-device privileges.

## Manual One-by-One Procedures (Recommended)

Run these one at a time to inspect behavior safely:

```bash
cd tests/

# 1) Image mount/unmount only
../env/bin/python -m pytest integration/test_image_manager.py::TestImageManagerIntegration::test_mount_and_unmount -m integration -v

# 2) SD loopback mount/unmount only
../env/bin/python -m pytest integration/test_sdcard_manager.py::TestSDCardManagerIntegration::test_loopback_mount -m integration -v

# 3) SD loopback partition detection only
../env/bin/python -m pytest integration/test_sdcard_manager.py::TestSDCardManagerIntegration::test_partition_detection -m integration -v

# 4) Optional chroot execution test (explicit opt-in)
../env/bin/python -m pytest integration/test_image_manager.py::TestImageManagerIntegration::test_chroot_execution -m integration --include-chroot-tests -v
```

### "qemu-arm-static not found"
Install with: `sudo apt-get install qemu-user-static`

### Stuck mounts
Run `sudo ./cleanup_all.sh` to force cleanup.

## CI/CD

Integration tests are marked with `@pytest.mark.integration` and excluded from default test runs. To run in CI:

```bash
# Skip integration tests (default)
pytest

# Include integration tests (requires sudo, test image)
cd tests/integration
./run_tests.py
```

## Safety Notes

- **Loopback by default**: `pytest -m integration` only executes non-device tests unless `--use-real-device` is provided
- **Real device checks**: Verifies device is removable and only one device present
- **Auto-cleanup**: Tests clean up mounts unless `--keep-mounted` flag set
- **Isolation**: Each test uses isolated temporary mount directories
