## Running the Tests

### Setup (One Time)
```bash
cd tests/integration
./setup_test_env.sh
```

### Run Unit Tests Only (Fast)
```bash
pytest -m unit
```

### Run Mock Tests Only (Fast)
```bash
pytest -m mock
```

### Run Unit + Mock (Default)
```bash
pytest
# or
pytest -m "not integration"
```

### Run Integration Tests (Manual)
```bash
# Recommended: use convenience script
cd tests/integration
./run_tests.py

# Or directly with venv python (safest by default: no device, no chroot)
../env/bin/python -m pytest -m integration

# Keep mounts for debugging
../env/bin/python -m pytest -m integration --keep-mounted

# Include chroot integration tests (still no real device)
../env/bin/python -m pytest -m integration --include-chroot-tests

# Use real SD card (auto-detect exactly one removable USB device)
../env/bin/python -m pytest -m integration --use-real-device

# Or use explicit device path
../env/bin/python -m pytest -m integration --use-real-device=/dev/sdb

# Device detection only (no tests)
./run_tests.py --mode detect

# Real-device tests with interactive selection + confirmation
./run_tests.py --mode device
```

### Manual One-by-One Safety Procedures
```bash
# 1) Prepare sudo and verify image exists
sudo -v
test -f tests/integration/fixtures/raspios-lite-test.img && echo "image ok"

# 2) Image mount/unmount only (no chroot commands)
../env/bin/python -m pytest tests/integration/test_image_manager.py::TestImageManagerIntegration::test_mount_and_unmount -m integration -v

# 3) SDCard loopback mount/unmount only (no real device)
../env/bin/python -m pytest tests/integration/test_sdcard_manager.py::TestSDCardManagerIntegration::test_loopback_mount -m integration -v

# 4) Optional: loopback partition detection only
../env/bin/python -m pytest tests/integration/test_sdcard_manager.py::TestSDCardManagerIntegration::test_partition_detection -m integration -v
```

### Run Specific Test
```bash
# Unit test
pytest tests/unit/test_mount_tracking.py

# Mock test
pytest tests/mock/test_usb_detection.py::TestUsbDetection::test_single_usb_device

# Integration test
../env/bin/python -m pytest tests/integration/test_image_manager.py -m integration -v
```
