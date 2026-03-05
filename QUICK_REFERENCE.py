#!/usr/bin/env python3
"""
Quick Reference: New Image/SD Card Manager API

This file provides a quick reference for the refactored API.
"""

# ============================================================================
# IMPORTS
# ============================================================================

from lib.managers import (
    create_manager,
    ImageFileManager,
    SDCardManager,
    LocalManager,
    SSHManager
)

# ============================================================================
# IMAGE FILE MANAGEMENT
# ============================================================================

# Using factory function
with create_manager('image', imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.put('/local/file.txt', '/etc/config.txt')

# Using class directly
with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    mgr.run('hostname')

# Custom mount path
with ImageFileManager(imagePath='/path/to/raspi.img', mountPath='/mnt/custom') as mgr:
    mgr.run('ls -la /')

# ============================================================================
# SD CARD MANAGEMENT (Known Device)
# ============================================================================

# Using factory function
with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
    mgr.run('apt-get update', sudo=True)

# Using class directly
with SDCardManager(devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')

# Works with mmcblk devices (auto-detects partition naming)
with SDCardManager(devicePath='/dev/mmcblk0') as mgr:
    # Automatically uses /dev/mmcblk0p1 and /dev/mmcblk0p2
    mgr.run('uname -a')

# ============================================================================
# SD CARD MANAGEMENT (USB Auto-Detection)
# ============================================================================

# Interactive selection via factory
with create_manager('sdcard', interactive=True) as mgr:
    # User is shown menu of USB devices
    # User selects device
    # User confirms selection
    mgr.run('hostname')

# Interactive selection via class method
with SDCardManager.from_interactive_selection() as mgr:
    mgr.run('hostname')

# Programmatic detection (no interaction)
devices = SDCardManager.detect_usb_devices()
print(f"Found {len(devices)} USB device(s)")
for dev in devices:
    print(f"  {dev['device']}: {dev['size']} {dev['vendor']} {dev['model']}")
    if dev['mounted']:
        print(f"    Mounted at: {', '.join(dev['mountpoints'])}")

# Use first detected device
if devices:
    with SDCardManager(devicePath=devices[0]['device']) as mgr:
        mgr.run('hostname')

# ============================================================================
# MOUNT REUSE BEHAVIOR
# ============================================================================

# Image files: Automatically reuses existing loop mounts
# - If image is already loop-mounted, reuses it (won't unmount on exit)
# - If image is not mounted, mounts it (will unmount on exit)

with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    mgr.run('hostname')
# Only unmounts if we mounted it

# SD cards: Automatically reuses existing partition mounts
# - If partitions already mounted, reuses them (won't unmount on exit)
# - If partitions not mounted, mounts them (will unmount on exit)

with SDCardManager(devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')
# Only unmounts partitions we mounted

# ============================================================================
# FILE OPERATIONS
# ============================================================================

with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    # Check existence
    exists = mgr.exists('/etc/hostname')

    # Read file
    content = mgr.read_file('/etc/hostname')

    # Write file
    mgr.write_file('/etc/hostname', 'raspberrypi\n')

    # Upload file
    mgr.put('/local/config.txt', '/boot/config.txt')

    # Download file
    mgr.get('/etc/hostname', '/tmp/hostname.txt')

    # Append to file
    mgr.append('/etc/hosts', '192.168.1.100 server')

# ============================================================================
# OTHER MANAGERS (Unchanged)
# ============================================================================

# Local execution
with create_manager('local') as mgr:
    mgr.run('uname -a')

# SSH execution
with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
    mgr.run('hostname')

# ============================================================================
# FORCE UNMOUNT (For Stuck Mounts)
# ============================================================================

# If processes are keeping mount busy, force-kill them before unmounting
with ImageFileManager(imagePath='/path/to/raspi.img', forceUnmount=True) as mgr:
    mgr.run('some-command')
# Will kill processes using mount before unmounting

with SDCardManager(devicePath='/dev/sdb', forceUnmount=True) as mgr:
    mgr.run('some-command')

# ============================================================================
# INTERACTIVE MANAGER CREATION
# ============================================================================

from lib.managers import interactive_create_manager

# Shows menu to select manager type and configure interactively
mgr = interactive_create_manager()
if mgr:
    with mgr:
        output, _, _ = mgr.run('hostname')
        print(output)

# ============================================================================
# MIGRATION FROM OLD API
# ============================================================================

# OLD (BROKEN):
# with create_manager('chroot', autoMount=True, imagePath='/path/to/raspi.img') as mgr:

# NEW:
with create_manager('image', imagePath='/path/to/raspi.img') as mgr:
    pass

# OLD (BROKEN):
# with create_manager('chroot', autoMount=True, imagePath='/dev/sdb') as mgr:

# NEW:
with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
    pass

# ============================================================================
# NOTES
# ============================================================================

# - `autoMount` parameter removed (always auto-mounts or reuses existing)
# - `keepMounted` parameter removed (smart mount tracking handles this)
# - 'chroot' mode removed (use 'image' or 'sdcard' instead)
# - Mount state is tracked automatically (only unmounts what was mounted by us)
# - Loop mount detection for image files (automatic reuse)
# - Partition detection using lsblk (handles all device naming schemes)
# - USB device auto-detection available
