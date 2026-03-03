# SD Card & Image Manager Refactor Plan

> Historical planning document. It captures pre-implementation design and may include examples from older APIs.
> For current behavior and examples, see `REFACTOR_COMPLETE.md`, `MIGRATION_GUIDE.md`, and `lib/cmd_manager.py`.

## Problem Analysis

### Current Issues

1. **Unclear Interface**: The `ImageManager` class handles both `.img` files and SD cards through the same `imagePath` parameter with auto-detection. This makes the user's intent unclear and makes error messages less helpful.

2. **Partition Handling Inconsistency**:
   - Image files: Uses `mnt_image.sh` which calculates offsets and mounts both boot and root partitions correctly
   - SD cards: Uses `_mount_drive()` which hardcodes partition naming (`device_path + "2"`, `device_path + "1"`)
   - Problem: SD card partition naming varies:
     - `/dev/sdb` → partitions are `/dev/sdb1`, `/dev/sdb2` ✓
     - `/dev/mmcblk0` → partitions are `/dev/mmcblk0p1`, `/dev/mmcblk0p2` ✗ (current code fails)
     - `/dev/nvme0n1` → partitions are `/dev/nvme0n1p1`, `/dev/nvme0n1p2` ✗ (current code fails)

3. **No Mount State Detection**: The code doesn't properly handle:
   - Individual partitions already mounted elsewhere
   - Boot and root partitions mounted at different locations
   - Partial mounts (e.g., only root mounted, boot unmounted)

4. **No USB Auto-detection**: Users must manually determine device paths. Would be better to:
   - Auto-detect USB storage devices
   - Show device info (size, label, existing mounts)
   - Let user select with confirmation

5. **Mixed Responsibilities**: `ImageManager` tries to handle both image files and physical devices, leading to code that's harder to maintain and test.

## Proposed Solution

### Architecture: Specialized Classes with Shared Base

```
BaseImageManager (abstract)
├── ImageFileManager (handles .img files)
└── SDCardManager (handles block devices)
```

### Key Design Decisions

1. **Explicit Manager Selection**: Users explicitly choose which manager type to instantiate:
   ```python
   # Clear intent - working with image file
   with ImageFileManager(imagePath='/path/to/raspi.img', autoMount=True) as mgr:
       mgr.run('apt-get update')

   # Clear intent - working with SD card
   with SDCardManager(devicePath='/dev/sdb', autoMount=True) as mgr:
       mgr.run('apt-get update')

   # Interactive with auto-detection
   with SDCardManager.from_interactive_selection() as mgr:
       mgr.run('apt-get update')
   ```

2. **Robust Partition Detection**:
   - Use `lsblk` for reliable partition enumeration
   - Support all block device naming schemes
   - Detect partition types (boot/root) by filesystem type and size heuristics

3. **Smart Mount State Management**:
   - Check existing mounts before attempting to mount
   - Option to reuse existing mounts if they match our needs
   - Handle partial mounts gracefully
   - Track what we mounted vs. what was already mounted (only unmount what we mounted)

4. **USB Device Auto-detection**:
   - Use `lsblk` to find removable USB devices
   - Display device info: name, size, label, vendor, partitions
   - Show current mount status
   - Interactive selection with confirmation

### Implementation Details

#### BaseImageManager (Abstract Base)

Common functionality for both image files and SD cards:
- chroot execution with QEMU
- ld.so.preload hack management
- QEMU setup
- File operations (put/get/exists)
- Mount state tracking
- Cleanup and unmount logic

Abstract methods to be implemented by subclasses:
- `_perform_mount()`: Actual mount logic
- `_perform_unmount()`: Actual unmount logic
- `_validate_target()`: Verify target exists and is correct type

#### ImageFileManager

Handles `.img` files:
- Validates file exists and is a regular file
- Uses existing `mnt_image.sh` script (already handles offsets correctly)
- Simpler than SD cards (no device detection needed)

#### SDCardManager

Handles block devices (SD cards, USB drives):
- Robust partition detection using `lsblk --json`
- Support for all partition naming schemes
- Smart mount state detection:
  - Check if partitions already mounted
  - Optionally reuse existing mounts
  - Track which mounts are ours vs. pre-existing
- USB device detection:
  - `lsblk --json` with filters for removable/USB devices
  - Display formatted table of devices
  - Interactive selection
  - Confirmation before proceeding

#### Partition Detection Algorithm

```python
def _detect_partitions(self, devicePath: str) -> dict:
    """
    Use lsblk to reliably detect partitions regardless of naming scheme.

    Returns:
        {
            'root': '/dev/sdb2',  # or /dev/mmcblk0p2, etc.
            'boot': '/dev/sdb1',
            'partitions': [
                {'name': 'sdb1', 'size': '256M', 'fstype': 'vfat', 'label': 'boot'},
                {'name': 'sdb2', 'size': '7.5G', 'fstype': 'ext4', 'label': 'rootfs'}
            ]
        }
    """
    # Use lsblk with JSON output for reliable parsing
    # Identify boot partition: typically FAT32, smaller size, labeled "boot"
    # Identify root partition: typically ext4, larger size, labeled "rootfs" or "root"
```

#### Mount State Detection Algorithm

```python
def _check_mount_state(self, partitions: dict) -> dict:
    """
    Check current mount status for boot and root partitions.

    Returns:
        {
            'root': {'mounted': True, 'mountpoint': '/media/user/rootfs'},
            'boot': {'mounted': True, 'mountpoint': '/media/user/boot'},
            'can_reuse': False  # True if both mounted and at correct locations
        }
    """
    # Parse /proc/mounts
    # Check if partitions are mounted
    # Determine if existing mounts can be reused
```

#### USB Device Detection

```python
@classmethod
def detect_usb_devices(cls) -> list[dict]:
    """
    Detect removable USB storage devices.

    Returns list of devices with info:
        [
            {
                'device': '/dev/sdb',
                'size': '8G',
                'vendor': 'SanDisk',
                'model': 'Ultra',
                'label': 'RASPI_OS',
                'partitions': [...],
                'mounted': True,
                'mountpoints': ['/media/user/boot', '/media/user/rootfs']
            }
        ]
    """
    # Use: lsblk --json -o NAME,SIZE,TYPE,VENDOR,MODEL,TRAN,RM,LABEL,MOUNTPOINT
    # Filter for: RM=1 (removable), TRAN=usb (USB transport)
```

### Backward Compatibility

To maintain backward compatibility with existing code:

1. Keep `ImageManager` as a facade that dispatches to the appropriate manager:
   ```python
   class ImageManager(BaseImageManager):
       """Legacy facade - dispatches to ImageFileManager or SDCardManager"""
       def __new__(cls, imagePath: str = None, **kwargs):
           if imagePath:
               if _is_block_device(imagePath):
                   return SDCardManager(devicePath=imagePath, **kwargs)
               else:
                   return ImageFileManager(imagePath=imagePath, **kwargs)
           else:
               # Manual mount mode - no auto-detection
               return BaseImageManager(**kwargs)
   ```

2. Update `create_manager()` to support new explicit modes:
   ```python
   # Old way (still works)
   mgr = create_manager('chroot', autoMount=True, imagePath='/dev/sdb')

   # New explicit ways
   mgr = create_manager('image', imagePath='/path/to/file.img', autoMount=True)
   mgr = create_manager('sdcard', devicePath='/dev/sdb', autoMount=True)
   mgr = create_manager('sdcard', autoDetect=True)  # Interactive selection
   ```

### Migration Path

1. **Phase 1**: Create new base class and specialized managers
   - Implement `BaseImageManager` with shared functionality
   - Implement `ImageFileManager` (simpler, reuse existing script)
   - Implement `SDCardManager` with robust partition detection

2. **Phase 2**: Add smart mount state management
   - Implement mount state detection
   - Add option to reuse existing mounts
   - Track what we mounted vs. pre-existing

3. **Phase 3**: Add USB auto-detection
   - Implement device detection
   - Add interactive selection
   - Add confirmation dialogs

4. **Phase 4**: Update `ImageManager` to be a facade
   - Maintain backward compatibility
   - Add deprecation warnings
   - Update documentation

5. **Phase 5**: Update examples and tests
   - Create examples for new managers
   - Add tests for partition detection
   - Add tests for mount state management

## Benefits

1. **Clarity**: Explicit manager types make code intent clear
2. **Robustness**: Proper partition detection works with all device types
3. **Safety**: Mount state detection prevents conflicts
4. **Usability**: Auto-detection reduces user burden
5. **Maintainability**: Separation of concerns makes code easier to understand and test
6. **Backward Compatible**: Existing code continues to work

## Testing Considerations

1. **Unit Tests**:
   - Partition name generation for different device types
   - lsblk output parsing
   - Mount state detection logic

2. **Integration Tests** (require actual devices or loop devices):
   - Mounting image files
   - Mounting SD cards with various partition schemes
   - Handling already-mounted partitions
   - USB device detection

3. **Mock Testing**:
   - Mock `lsblk` output for different device types
   - Mock `/proc/mounts` for various mount states
   - Test error handling paths

## Security Considerations

1. **Confirmation Required**: Always confirm before mounting/unmounting external devices
2. **Display Device Info**: Show size, label, existing data to prevent accidents
3. **Privilege Escalation**: Use `sudo` only when necessary, validate paths
4. **Path Validation**: Validate device paths to prevent injection attacks

## Alternative Considered: Single Class with Strategy Pattern

Instead of separate classes, could use strategy pattern:
```python
class ImageManager:
    def __init__(self, target: ImageFile | SDCard):
        self.target = target  # Strategy object handles mounting
```

**Rejected because**:
- More complex for users (need to construct strategy objects)
- Less explicit in API
- Harder to add class methods like `SDCardManager.from_interactive_selection()`
- Specialized classes provide better type hints and IDE support

## Questions for Discussion

1. Should we support mounting image files that are already loop-mounted?
2. Should we auto-detect and warn about existing data on unmounted partitions?
3. Should we support multiple SD cards connected simultaneously?
4. Should we add a "dry-run" mode that shows what would be mounted without doing it?
5. Should we support non-Raspberry Pi images (different partition layouts)?

## Example Usage After Refactor

```python
# Example 1: Image file (explicit)
with ImageFileManager(imagePath='/path/to/raspi.img', autoMount=True) as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.put('/local/config.txt', '/boot/config.txt')

# Example 2: SD card with known device path
with SDCardManager(devicePath='/dev/sdb', autoMount=True) as mgr:
    mgr.run('hostname')
    mgr.run('apt-get install -y vim', sudo=True)

# Example 3: SD card with auto-detection
with SDCardManager.from_interactive_selection() as mgr:
    # User is shown list of USB devices and selects one
    mgr.run('uname -a')

# Example 4: SD card with auto-detection (programmatic)
devices = SDCardManager.detect_usb_devices()
print(f"Found {len(devices)} USB devices")
for dev in devices:
    print(f"  {dev['device']}: {dev['size']} {dev['vendor']} {dev['model']}")

# Select first device
with SDCardManager(devicePath=devices[0]['device'], autoMount=True) as mgr:
    mgr.run('hostname')

# Example 5: Legacy compatibility (still works)
with create_manager('chroot', autoMount=True, imagePath='/dev/sdb') as mgr:
    mgr.run('apt-get update')  # Internally uses SDCardManager

# Example 6: Reuse existing mounts
with SDCardManager(devicePath='/dev/sdb', reuseExistingMounts=True) as mgr:
    # If partitions already mounted, reuse them
    # Only unmount what we mounted
    mgr.run('ls -la /')
```
