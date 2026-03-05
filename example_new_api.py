#!/usr/bin/env python3
"""
Examples demonstrating the new ImageFileManager and SDCardManager API.

Shows usage patterns for:
- Image files with loop mount detection
- SD cards with robust partition detection
- USB device auto-detection
- Mount state management
"""

from lib.managers import create_manager, ImageFileManager, SDCardManager


def demo_image_file():
    """Example: Work with an image file (auto-detects existing loop mounts)"""
    print("\n=== IMAGE FILE MANAGER ===")

    imagePath = './raspios.img'

    # ImageFileManager automatically:
    # 1. Checks if image is already loop-mounted
    # 2. Reuses existing mount if found (won't unmount on cleanup)
    # 3. Mounts if not already mounted (will unmount on cleanup)

    try:
        with ImageFileManager(imagePath=imagePath) as mgr:
            # Work with the image
            output, error, status = mgr.run('uname -m')
            print(f"Architecture: {output.strip()}")

            output, error, status = mgr.run('df -h /')
            print(f"Disk space:\n{output}")

            # File operations work transparently
            mgr.put('/local/config.txt', '/boot/config.txt')
            content = mgr.read_file('/etc/hostname')
            print(f"Hostname: {content.strip()}")

        # Auto-unmounts only if we mounted it
        print("Image manager closed (unmounted if we mounted it)")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


def demo_sdcard_known_device():
    """Example: Work with SD card using known device path"""
    print("\n=== SD CARD MANAGER (Known Device) ===")

    # Works with any device naming scheme:
    # - /dev/sdb (USB drive)
    # - /dev/mmcblk0 (SD card reader)
    # - /dev/nvme0n1 (NVMe device)

    devicePath = '/dev/sdb'

    try:
        with SDCardManager(devicePath=devicePath) as mgr:
            # SDCardManager automatically:
            # 1. Detects partitions using lsblk (handles all naming schemes)
            # 2. Identifies boot (vfat) and root (ext4) partitions
            # 3. Reuses existing mounts if already mounted
            # 4. Only unmounts what it mounted

            output, error, status = mgr.run('hostname')
            print(f"Hostname: {output.strip()}")

            output, error, status = mgr.run('cat /proc/cpuinfo | grep Model')
            print(f"CPU: {output.strip()}")

            # Modify configuration
            mgr.append('/etc/hosts', '192.168.1.100 myserver')

            # Install packages
            mgr.run('apt-get update', sudo=True)
            mgr.run('apt-get install -y vim', sudo=True)

        print("SD card unmounted (only what we mounted)")

    except ValueError as e:
        print(f"Error: {e}")
    except RuntimeError as e:
        print(f"Error: {e}")


def demo_sdcard_mmcblk():
    """Example: SD card with mmcblk device (different partition naming)"""
    print("\n=== SD CARD MANAGER (mmcblk device) ===")

    # This demonstrates handling of mmcblk devices
    # Partitions are /dev/mmcblk0p1 and /dev/mmcblk0p2 (not mmcblk01, mmcblk02)

    devicePath = '/dev/mmcblk0'

    try:
        with SDCardManager(devicePath=devicePath) as mgr:
            # Partition detection automatically handles the 'p' prefix
            output, error, status = mgr.run('uname -a')
            print(f"System: {output.strip()}")

            # Read boot config
            config = mgr.read_file('/boot/config.txt')
            print(f"Boot config (first 5 lines):")
            for line in config.split('\n')[:5]:
                print(f"  {line}")

        print("Done")

    except Exception as e:
        print(f"Error: {e}")


def demo_usb_auto_detection():
    """Example: Auto-detect and select USB device interactively"""
    print("\n=== SD CARD MANAGER (USB Auto-Detection) ===")

    try:
        # First, programmatically list available devices
        devices = SDCardManager.detect_usb_devices()

        if not devices:
            print("No USB devices found")
            return

        print(f"Found {len(devices)} USB device(s):")
        for dev in devices:
            mountStatus = "mounted" if dev['mounted'] else "unmounted"
            print(f"  {dev['device']}: {dev['size']} {dev['vendor']} {dev['model']} [{mountStatus}]")
            if dev['mountpoints']:
                for mp in dev['mountpoints']:
                    print(f"    -> {mp}")

        # Interactive selection with confirmation
        print("\nUsing interactive selection:")
        with SDCardManager.from_interactive_selection() as mgr:
            # User is shown list and prompted to select
            output, error, status = mgr.run('hostname')
            print(f"Hostname: {output.strip()}")

            mgr.run('apt-get update', sudo=True)

        print("Done")

    except RuntimeError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


def demo_factory_function():
    """Example: Using the factory function for different modes"""
    print("\n=== FACTORY FUNCTION ===")

    # Image file
    print("\n1. Image file mode:")
    try:
        with create_manager('image', imagePath='/path/to/raspios.img') as mgr:
            output, _, _ = mgr.run('hostname')
            print(f"  Hostname: {output.strip()}")
    except Exception as e:
        print(f"  Error: {e}")

    # SD card with known device
    print("\n2. SD card mode (known device):")
    try:
        with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
            output, _, _ = mgr.run('hostname')
            print(f"  Hostname: {output.strip()}")
    except Exception as e:
        print(f"  Error: {e}")

    # SD card with interactive selection
    print("\n3. SD card mode (interactive):")
    try:
        with create_manager('sdcard', interactive=True) as mgr:
            output, _, _ = mgr.run('hostname')
            print(f"  Hostname: {output.strip()}")
    except Exception as e:
        print(f"  Error: {e}")


def demo_mount_reuse():
    """Example: Demonstrates automatic mount reuse"""
    print("\n=== MOUNT REUSE DEMONSTRATION ===")

    imagePath = '/path/to/raspios.img'

    print("First manager - will mount the image:")
    try:
        with ImageFileManager(imagePath=imagePath) as mgr1:
            output, _, _ = mgr1.run('hostname')
            print(f"  Manager 1 hostname: {output.strip()}")

            # Manually mount the image in a second terminal, then:
            print("\n  (Image is now mounted)")
            print("\nSecond manager - will reuse existing mount:")

            with ImageFileManager(imagePath=imagePath) as mgr2:
                output, _, _ = mgr2.run('hostname')
                print(f"  Manager 2 hostname: {output.strip()}")
                print("  (Using same mount as manager 1)")

            print("\n  Manager 2 closed - did NOT unmount (didn't mount it)")

        print("Manager 1 closed - did unmount (it mounted it)")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    # Run individual demos (comment out as needed)

    demo_image_file()
    # demo_sdcard_known_device()
    # demo_sdcard_mmcblk()
    # demo_usb_auto_detection()
    # demo_factory_function()
    # demo_mount_reuse()

    print("\nTo run examples, uncomment the desired demo function calls in __main__")
    print("Make sure to update device/image paths to match your system")
