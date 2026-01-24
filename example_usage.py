#!/usr/bin/env python3
"""
Example usage of the multi-location OS manager.

Demonstrates how to use the same interface for localhost, remote SSH, and chroot operations.
"""

from cmd_manager import create_manager


def demo_local():
    """Example: Working with localhost"""
    print("\n=== LOCAL HOST OPERATIONS ===")

    with create_manager('local') as mgr:
        # Run a simple command
        output, error, status = mgr.run('uname -a')
        print(f"System info: {output.strip()}")

        # Check if a file exists
        if mgr.exists('/etc/hostname'):
            print("/etc/hostname exists")

        # Create a test file
        test_file = '/tmp/test_append.txt'
        mgr.append(test_file, 'Line 1: Hello from local')
        mgr.append(test_file, ['Line 2: Multiple', 'Line 3: Lines'])

        # Verify
        output, _, _ = mgr.run(f'cat {test_file}')
        print(f"Test file contents:\n{output}")


def demo_ssh():
    """Example: Working with remote host via SSH"""
    print("\n=== REMOTE SSH OPERATIONS ===")

    # Adjust these parameters for your setup
    hostName = '192.168.1.100'
    userName = 'pi'
    # key_filename = '/home/user/.ssh/id_rsa'  # Optional

    try:
        with create_manager('ssh', hostName=hostName, userName=userName) as mgr:
            # Run a command
            output, error, status = mgr.run('hostname')
            print(f"Remote hostname: {output.strip()}")

            # Run with sudo
            output, error, status = mgr.run('whoami', sudo=True)
            print(f"Sudo user: {output.strip()}")

            # Upload a file
            # mgr.put('/local/path/file.txt', '/remote/path/file.txt')

            # Append to a file (with sudo if needed)
            mgr.append('/tmp/remote_test.txt', 'Added from SSH manager', sudo=False)

    except Exception as e:
        print(f"SSH connection failed: {e}")


def demo_chroot():
    """Example: Working with mounted ARM image via chroot (legacy - manual mount)"""
    print("\n=== CHROOT (ARM IMAGE) OPERATIONS - Manual Mount ===")

    mountPath = '/mnt/image'

    # Assumes the ARM image is already mounted at /mnt/image
    with create_manager('chroot', mountPath=mountPath) as mgr:
        # Run ARM commands via QEMU emulation
        output, error, status = mgr.run('uname -m')
        print(f"Architecture: {output.strip()}")

        output, error, status = mgr.run('cat /etc/os-release | grep PRETTY_NAME')
        print(f"OS: {output.strip()}")

        # Modify files in the chroot filesystem
        mgr.append('/etc/profile', '# Custom profile modification')

        # Install packages (with sudo)
        # mgr.run('apt-get update', sudo=True)
        # mgr.run('apt-get install -y vim', sudo=True)

        # Copy file into the image
        # mgr.put('/local/config.txt', '/etc/myapp/config.txt')


def demo_chroot_automount_image():
    """Example: Auto-mount image file and work with it"""
    print("\n=== CHROOT AUTO-MOUNT (IMAGE FILE) ===")

    # Path to your Raspberry Pi image file
    imagePath = '/path/to/raspi.img'

    # Auto-mount will:
    # 1. Detect it's an image file
    # 2. Mount it at /mnt/image (default)
    # 3. Apply ld.so.preload hack for apt-get support
    # 4. Auto-unmount when done (unless keep_mounted=True)

    try:
        with create_manager('chroot', autoMount=True,
                  imagePath=imagePath) as mgr:
            # Work with the image transparently
            output, error, status = mgr.run('uname -m')
            print(f"Architecture: {output.strip()}")

            output, error, status = mgr.run('df -h /')
            print(f"Disk space:\n{output}")

            # Install packages
            # mgr.run('apt-get update', sudo=True)
            # mgr.run('apt-get install -y htop', sudo=True)

        # Image is automatically unmounted here
        print("Image unmounted automatically")

    except FileNotFoundError:
        print(f"Image not found: {imagePath} - update path and try again")
    except Exception as e:
        print(f"Error: {e}")


def demo_chroot_automount_sdcard():
    """Example: Auto-mount SD card and work with it"""
    print("\n=== CHROOT AUTO-MOUNT (SD CARD) ===")

    # Path to SD card block device (e.g., /dev/sdb, /dev/mmcblk0)
    sdCardDevice = '/dev/sdb'

    # Auto-mount will:
    # 1. Detect it's a block device
    # 2. Mount partition 2 (root) and partition 1 (boot)
    # 3. Apply ld.so.preload hack for apt-get support
    # 4. Auto-unmount when done

    try:
        with create_manager('chroot', autoMount=True,
                  imagePath=sdCardDevice) as mgr:
            # Work with the SD card OS
            output, error, status = mgr.run('hostname')
            print(f"Hostname: {output.strip()}")

            output, error, status = mgr.run('uname -a')
            print(f"System: {output.strip()}")

            # Modify configuration
            mgr.append('/etc/hosts', '192.168.1.100 myserver')

        # SD card is automatically unmounted here
        print("SD card unmounted automatically")

    except FileNotFoundError:
        print(f"Device not found: {sdCardDevice} - check device path")
    except Exception as e:
        print(f"Error: {e}")


def demo_chroot_keep_mounted():
    """Example: Keep image mounted for development workflow"""
    print("\n=== CHROOT AUTO-MOUNT (KEEP MOUNTED) ===")

    imagePath = '/path/to/raspi.img'

    # Use keep_mounted=True to leave the image mounted after operations
    # This is useful during development when you'll make multiple changes

    try:
        with create_manager('chroot', autoMount=True,
                  imagePath=imagePath,
                  keepMounted=True) as mgr:

            mgr.run('echo "Development mode" > /tmp/dev_flag')
            print("Image remains mounted for further operations")

        # Image stays mounted - you can create another manager to continue work
        print("Image still mounted at /mnt/image for continued development")

        # Later, when you're done, manually unmount:
        # with create_manager('chroot', mountPath='/mnt/image',
        #                    auto_mount=False) as mgr:
        #     pass  # Just use for cleanup
        # Or use subprocess: subprocess.run('sudo bash os/unmnt_image.sh /mnt/image', shell=True)

    except FileNotFoundError:
        print(f"Image not found: {image_path} - update path and try again")
    except Exception as e:
        print(f"Error: {e}")


def demo_transparent_usage(mgr):
    """
    Example: Same code works with any manager type!

    This function doesn't care if it's working on localhost, remote SSH, or chroot.
    The caller decides by passing the appropriate manager instance.
    """
    print("\n=== TRANSPARENT USAGE ===")

    # This exact same code works regardless of manager type
    mgr.run('mkdir -p /tmp/testdir')
    mgr.append('/tmp/testdir/config.txt', 'Setting=Value')

    if mgr.exists('/tmp/testdir/config.txt'):
        output, _, _ = mgr.run('cat /tmp/testdir/config.txt')
        print(f"Config contents: {output}")

    # Cleanup
    mgr.run('rm -rf /tmp/testdir')


def demo_all_transparent():
    """Demonstrate calling the same function with different manager types"""

    # Same function, different execution contexts
    print("\nCalling transparent_usage() with LOCAL manager:")
    with create_manager('local') as mgr:
        demo_transparent_usage(mgr)

    # Uncomment to test with SSH
    # print("\nCalling transparent_usage() with SSH manager:")
    # with create_manager('ssh', hostname='192.168.1.100', username='pi') as mgr:
    #     demo_transparent_usage(mgr)

    # Uncomment to test with chroot
    # print("\nCalling transparent_usage() with CHROOT manager:")
    # with create_manager('chroot', mount_path='/mnt/image') as mgr:
    #     demo_transparent_usage(mgr)


if __name__ == '__main__':
    # Run local demo
    demo_local()

    # Uncomment to run other demos
    # demo_ssh()
    # demo_chroot()  # Legacy manual mount
    # demo_chroot_automount_image()  # Auto-mount image file
    # demo_chroot_automount_sdcard()  # Auto-mount SD card
    # demo_chroot_keep_mounted()  # Keep mounted for development

    # Demonstrate transparent usage
    demo_all_transparent()

    print("\n=== DONE ===")
