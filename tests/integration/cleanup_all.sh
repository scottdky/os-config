#!/bin/bash
# Emergency cleanup script for stuck mounts and loop devices

echo "Cleaning up all test mounts and loop devices..."
echo ""

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run with sudo"
    exit 1
fi

# Find and unmount all pytest_mount_* directories
echo "Unmounting pytest temporary directories..."
for mount_point in /tmp/pytest_mount_*; do
    if [ -d "$mount_point" ]; then
        echo "  Unmounting: $mount_point"
        umount -R "$mount_point" 2>/dev/null || true
        rm -rf "$mount_point"
    fi
done

# Find and detach loop devices used by test images
echo ""
echo "Detaching test image loop devices..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_IMAGE="$SCRIPT_DIR/fixtures/raspios-lite-test.img"

if [ -f "$TEST_IMAGE" ]; then
    LOOP_DEVS=$(losetup -j "$TEST_IMAGE" | cut -d: -f1)
    if [ -n "$LOOP_DEVS" ]; then
        for loop_dev in $LOOP_DEVS; do
            echo "  Detaching: $loop_dev"
            losetup -d "$loop_dev" 2>/dev/null || true
        done
    else
        echo "  No loop devices found for test image"
    fi
else
    echo "  Test image not found: $TEST_IMAGE"
fi

# List remaining loop devices (for info)
echo ""
echo "Remaining loop devices:"
losetup -l

echo ""
echo "✓ Cleanup complete"
