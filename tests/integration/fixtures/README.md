# Test Fixtures

This directory stores test image files used by integration tests.

## Setup

Run the setup script to download/create a minimal test image:

```bash
cd tests/integration
./setup_test_env.sh
```

This will create `raspios-lite-test.img` (~500MB) for testing.

## Manual Setup (Alternative)

If the script fails, manually download a Raspberry Pi OS Lite image:

```bash
cd fixtures/
wget https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-03-12/2024-03-12-raspios-bookworm-arm64-lite.img.xz
xz -d 2024-03-12-raspios-bookworm-arm64-lite.img.xz
mv 2024-03-12-raspios-bookworm-arm64-lite.img raspios-lite-test.img
```

## Cleanup

These files are git-ignored. To remove:

```bash
rm -f *.img *.img.gz *.img.xz
```
