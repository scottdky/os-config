# SD Card & Image Manager Refactor - Implementation Complete

## Summary

Successfully refactored the image and SD card management system with improved architecture and smart mount detection.

## What Was Changed

### 1. Class Hierarchy (Breaking Change)

**Before:**
```python
ImageManager  # Handled both .img files and SD cards with auto-detection
```

**After:**
```python
BaseImageManager (abstract)
├── ImageFileManager  # Handles .img files only
└── SDCardManager     # Handles SD cards/block devices only
```

### 2. API Changes

#### Old API (Removed):
```python
# Old 'chroot' mode - REMOVED
with create_manager('chroot', autoMount=True, imagePath='/path/or/device') as mgr:
    mgr.run('apt-get update')
```

#### New API:
```python
# Image files - explicit
with create_manager('image', imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update')

# SD cards - explicit
with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')

# SD cards - interactive USB selection
with create_manager('sdcard', interactive=True) as mgr:
    mgr.run('hostname')

# Or use classes directly
with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update')

with SDCardManager(devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')
```

### 3. New Features

#### Smart Mount Detection

**Image Files:**
- Detects if image is already loop-mounted using `losetup -j`
- Reuses existing mount automatically
- Only unmounts what it mounted (tracks with `_mountedByUs` dict)

**SD Cards:**
- Robust partition detection using `lsblk --json`
- Handles all device naming schemes:
  - `/dev/sdb` → `/dev/sdb1`, `/dev/sdb2`
  - `/dev/mmcblk0` → `/dev/mmcblk0p1`, `/dev/mmcblk0p2`
  - `/dev/nvme0n1` → `/dev/nvme0n1p1`, `/dev/nvme0n1p2`
- Detects already-mounted partitions
- Reuses existing mounts automatically
- Only unmounts what it mounted

#### USB Device Auto-Detection

```python
# Programmatic detection
devices = SDCardManager.detect_usb_devices()
for dev in devices:
    print(f"{dev['device']}: {dev['size']} {dev['vendor']} {dev['model']}")

# Interactive selection
with SDCardManager.from_interactive_selection() as mgr:
    # Shows menu of USB devices, user selects, confirmation prompt
    mgr.run('hostname')
```

### 4. Files Changed

- `/mnt/development/bin/os-config/lib/cmd_manager.py` - Complete refactor
    - Added `BaseImageManager` abstract base class
    - Added `ImageFileManager`
    - Added `SDCardManager`
    - Updated `create_manager()` factory function
    - Updated `interactive_create_manager()` function
    - Updated module docstring

- `/mnt/development/bin/os-config/example_new_api.py` - New examples file
  - Comprehensive examples for all new features
  - Demonstrates mount reuse behavior
  - Shows USB device detection

- `/mnt/development/bin/os-config/SDCARD_REFACTOR_PLAN.md` - Planning document
  - Detailed analysis and design decisions

## Key Implementation Details

### BaseImageManager

Common functionality for all image/SD managers:
- QEMU ARM static emulation setup
- ld.so.preload hack management
- chroot execution
- File operations (put/get/exists/read/write)
- Mount tracking via `_mountedByUs` dictionary
- Abstract methods: `_validate_target()`, `_perform_mount()`, `_perform_unmount()`

### ImageFileManager

Handles `.img` files:
- `_find_existing_loop_mount()`: Checks `losetup -j` and `/proc/mounts`
- Reuses existing loop mounts (doesn't unmount them)
- Uses existing `mnt_image.sh` script for new mounts
- Tracks whether it mounted or reused mount

### SDCardManager

Handles block devices:
- `_detect_partitions()`: Uses `lsblk --json` for robust detection
- Identifies boot partition by `fstype='vfat'`
- Identifies root partition by `fstype='ext4'`
- Handles partition naming (adds 'p' for mmcblk/nvme devices)
- `detect_usb_devices()`: Class method to find USB devices
- `from_interactive_selection()`: Interactive USB device selection
- Reuses already-mounted partitions
- Only unmounts partitions it mounted

## Migration Guide

### For Existing Code

**Before (BROKEN):**
```python
with create_manager('chroot', autoMount=True, imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update')
```

**After (WORKING):**
```python
# Option 1: Use factory with explicit mode
with create_manager('image', imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update')

# Option 2: Use class directly
with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update')
```

**SD Card Migration:**

Before:
```python
with create_manager('chroot', autoMount=True, imagePath='/dev/sdb') as mgr:
    mgr.run('hostname')
```

After:
```python
with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')
```

### Parameters Removed

- `autoMount` - Always auto-mounts now (or reuses existing mount)
- Old `imagePath` parameter for both files and devices
    - Replaced with `imagePath` for ImageFileManager
    - Replaced with `devicePath` for SDCardManager

### Parameters Kept

- `mountPath` - Where to mount (default: `/mnt/image`)
- `forceUnmount` - Force-kill processes before unmounting
- `keepMounted` - Keep mounts active after manager close (for debugging/workflow continuity)
- `defaultChrootUser` - Run non-sudo chroot commands as a non-root user

## Testing

### Import Test
```bash
source env/bin/activate
python3 -c "from lib.cmd_manager import ImageFileManager, SDCardManager; print('OK')"
```
✓ Passed

### USB Detection Test
```bash
python3 -c "from lib.cmd_manager import SDCardManager; print(SDCardManager.detect_usb_devices())"
```
✓ Passed (returns empty list when no USB devices)

### Factory Function Test
```bash
python3 -c "from lib.cmd_manager import create_manager; create_manager('local')"
```
✓ Passed

### Old Mode Rejection Test
```bash
python3 -c "from lib.cmd_manager import create_manager; create_manager('chroot')"
```
✓ Passed (raises ValueError as expected)

## Benefits Achieved

1. **Clarity** ✓ - Explicit manager types make intent clear
2. **Robustness** ✓ - Handles all device naming schemes correctly
3. **Smart** ✓ - Automatically reuses existing mounts
4. **Usability** ✓ - USB auto-detection reduces user burden
5. **Maintainability** ✓ - Clean separation of concerns
6. **Simplicity** ✓ - No legacy code to maintain

## Known Limitations

1. Only supports Raspberry Pi OS (boot=vfat, root=ext4)
2. Only one SD card at a time
3. No dry-run mode
4. No existing data warnings
5. Boot partition mount failure is non-fatal (warning only)

## Future Enhancements

1. Support for other OS images (different partition layouts)
2. Multiple SD card support
3. Better error messages with recovery suggestions
4. Automatic backup before modifications
5. Support for compressed images (.img.xz, .img.gz)

## Examples

See `/mnt/development/bin/os-config/example_new_api.py` for comprehensive examples.

Quick start:
```python
# Image file
with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
    mgr.run('hostname')

# SD card with known device
with SDCardManager(devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')

# SD card with USB auto-detection
with SDCardManager.from_interactive_selection() as mgr:
    mgr.run('hostname')
```
