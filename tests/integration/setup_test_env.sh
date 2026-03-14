#!/bin/bash
# Setup integration test environment by downloading/creating minimal test image

set -euo pipefail

# If invoked via sudo, rerun as original user to keep workspace access.
# Privileged operations are executed with sudo only where required.
if [[ "${EUID}" -eq 0 && -n "${SUDO_USER:-}" ]]; then
    exec sudo -u "${SUDO_USER}" -H bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
TEST_IMAGE="$FIXTURES_DIR/raspios-lite-test.img"

echo "Setting up integration test environment..."
echo "Script directory: $SCRIPT_DIR"
echo "Target: $TEST_IMAGE"

mkdir -p "$FIXTURES_DIR"

# Check if test image already exists
if [[ -f "$TEST_IMAGE" ]]; then
    echo "Test image already exists: $TEST_IMAGE"
    echo "Size: $(du -h "$TEST_IMAGE" | cut -f1)"
    read -p "Re-download or rebuild? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Using existing image."
        exit 0
    fi
    rm -f "$TEST_IMAGE"
fi

echo ""
echo "Select download option:"
echo "  1) Download latest Raspberry Pi OS Lite (ARM64) - ~400MB download"
echo "  2) Create minimal test image (50MB) - fast but limited functionality"
echo ""
read -p "Choice (1/2): " -n 1 -r CHOICE
echo

if [[ "$CHOICE" == "1" ]]; then
    echo "Downloading Raspberry Pi OS Lite..."

    #IMAGE_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-03-12/2024-03-12-raspios-bookworm-arm64-lite.img.xz"
    IMAGE_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2025-12-04/2025-12-04-raspios-trixie-arm64-lite.img.xz"

    echo "Downloading from: $IMAGE_URL"
    cd "$FIXTURES_DIR"

    wget -O raspios-lite.img.xz "$IMAGE_URL"

    echo "Extracting..."
    xz -d raspios-lite.img.xz

    mv -f raspios-lite.img "$TEST_IMAGE"

    echo "Downloaded: $(du -h "$TEST_IMAGE" | cut -f1)"

elif [[ "$CHOICE" == "2" ]]; then
    echo "Creating minimal test image..."

    stagingImage="$(mktemp /tmp/raspios-lite-test.XXXXXX.img)"
    tempMount=""
    loopDev=""

    cleanup() {
        if [[ -n "$tempMount" && -d "$tempMount" ]]; then
            sudo umount "$tempMount" 2>/dev/null || true
            rmdir "$tempMount" 2>/dev/null || true
        fi
        if [[ -n "$loopDev" ]]; then
            sudo losetup -d "$loopDev" 2>/dev/null || true
        fi
        if [[ -n "${stagingImage:-}" && -f "$stagingImage" ]]; then
            rm -f "$stagingImage" 2>/dev/null || true
        fi
    }
    trap cleanup EXIT

    # Create a minimal bootable image structure
    # Size: 50MB (10MB boot + 40MB root)
    dd if=/dev/zero of="$stagingImage" bs=1M count=50 status=progress

    # Partition the image
    echo "Partitioning..."
    sudo parted -s "$stagingImage" mklabel msdos
    sudo parted -s "$stagingImage" mkpart primary fat32 1MiB 11MiB
    sudo parted -s "$stagingImage" mkpart primary ext4 11MiB 100%
    sudo parted -s "$stagingImage" set 1 boot on

    # Setup loop device
    loopDev="$(sudo losetup -f --show -P "$stagingImage")"
    echo "Using loop device: $loopDev"

    # Wait for partitions
    sleep 1

    # Format partitions
    echo "Formatting boot partition..."
    sudo mkfs.vfat -F 32 "${loopDev}p1"

    echo "Formatting root partition..."
    sudo mkfs.ext4 -F "${loopDev}p2"

    # Mount and create minimal structure
    tempMount="$(mktemp -d /tmp/raspios-mount.XXXXXX)"
    sudo mount "${loopDev}p2" "$tempMount"

    echo "Creating directory structure..."
    sudo mkdir -p "$tempMount"/{boot,bin,sbin,usr/bin,usr/sbin,etc,home,root,tmp,var,proc,sys,dev}

    # Create minimal config files
    echo "Creating minimal system files..."
    echo "minimal-test" | sudo tee "$tempMount/etc/hostname" > /dev/null
    echo "127.0.0.1 localhost" | sudo tee "$tempMount/etc/hosts" > /dev/null

    # Close privileged resources before copying into workspace
    sudo umount "$tempMount"
    rmdir "$tempMount"
    tempMount=""

    sudo losetup -d "$loopDev"
    loopDev=""

    mv -f "$stagingImage" "$TEST_IMAGE"
    stagingImage=""

    trap - EXIT
    echo "Created minimal image: $(du -h "$TEST_IMAGE" | cut -f1)"

else
    echo "Invalid choice. Exiting."
    exit 1
fi

echo ""
echo "✓ Setup complete!"
echo ""
echo "Test image ready at: $TEST_IMAGE"
echo "Size: $(du -h "$TEST_IMAGE" | cut -f1)"
echo ""
echo "Run integration tests with:"
echo "  cd tests/integration"
echo "  ./run_tests.py"
