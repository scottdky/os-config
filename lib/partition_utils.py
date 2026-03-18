"""
Utility functions for partition and filesystem management.
Requires `run_local()` available on the provided manager instance for host-side commands.
"""

import json
import logging
from contextlib import contextmanager
from typing import Any, Generator

from lib.managers.image import BaseImageManager, ImageFileManager, SDCardManager

logger = logging.getLogger(__name__)

def _get_target_path(mgr: BaseImageManager) -> str:
    """Extract the target path (image or device) from the manager."""
    if isinstance(mgr, ImageFileManager):
        return mgr.imagePath
    elif isinstance(mgr, SDCardManager):
        return mgr.devicePath
    else:
        raise ValueError("Provided manager must be an ImageFileManager or SDCardManager")

@contextmanager
def target_block_device(mgr: BaseImageManager) -> Generator[str, None, None]:
    """Yield a block device path for the target managed by the manager.

    If the target is an image file, attaches it to a loop device,
    scans partitions (-P), and detaches it upon completion.
    """
    targetPath = _get_target_path(mgr)

    if isinstance(mgr, SDCardManager):
        yield targetPath
        return

    # It must be an ImageFileManager
    res = mgr.run_local(f"losetup -P -f --show {targetPath}", sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to attach image to loop device: {res.stderr}")

    loop_dev = res.stdout.strip()
    try:
        yield loop_dev
    finally:
        mgr.run_local(f"losetup -d {loop_dev}", sudo=True)

def expand_image_file(mgr: ImageFileManager, additional_mb: int) -> None:
    """Expand the physical capacity of an image file."""
    if not isinstance(mgr, ImageFileManager):
        raise ValueError("expand_image_file only applies to image files.")

    if additional_mb <= 0:
        return

    targetPath = _get_target_path(mgr)
    cmd = f"truncate -s +{additional_mb}M {targetPath}"
    res = mgr.run_local(cmd, sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to expand image file: {res.stderr}")

def get_partitions(mgr: BaseImageManager) -> list[dict[str, Any]]:
    """Get partition layout from the target using lsblk --json."""
    with target_block_device(mgr) as device:
        cmd = f"lsblk -J -b -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT,PARTTYPENAME {device}"
        res = mgr.run_local(cmd, sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to read partition info: {res.stderr}")

        data = json.loads(res.stdout)
        if "blockdevices" in data and len(data["blockdevices"]) > 0:
            dev_info = data["blockdevices"][0]
            if "children" in dev_info:
                return dev_info["children"]
        return []

def get_free_space(mgr: BaseImageManager, device: str) -> dict[str, str]:
    """Parse `parted print free` to find the last free sector."""
    # Find free space at the end
    res = mgr.run_local(f"parted -sm {device} unit MB print free | tail -1", sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to read parted print free: {res.stderr}")

    # Output looks like: 1:1234MB:2345MB:1111MB:free;
    parts = res.stdout.strip().split(':')
    if len(parts) >= 4 and 'free' in res.stdout.lower():
        return {
            'start': parts[1],
            'end': parts[2],
            'size': parts[3]
        }
    return {}

def add_partition(mgr: BaseImageManager, label: str, size_mb: int = 0, fs: str = 'ext4') -> None:
    """Create a new partition and format it.
    If size_mb is 0, uses all remaining space.
    """
    if size_mb < 0:
        raise ValueError("size_mb cannot be negative")

    with target_block_device(mgr) as device:
        # Before adding, we find the unallocated space extent
        free_space = get_free_space(mgr, device)
        if not free_space:
            raise RuntimeError("No free space found at the end of the device.")

        start = free_space['start']
        if size_mb > 0:
            start_num = float(start.replace('MB', ''))
            stop = f"{int(start_num + size_mb)}MB"
        else:
            stop = free_space['end']

        part_cmd = f"parted -s {device} mkpart primary {fs} {start} {stop}"
        res = mgr.run_local(part_cmd, sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to create partition: {res.stderr}")

        # Refresh partition table map so we can format it
        mgr.run_local("udevadm settle", sudo=True)

        # After mkpart, find the latest partition logic based on parted print
        res = mgr.run_local(f"parted -sm {device} print | tail -1", sudo=True)
        part_num = res.stdout.strip().split(':')[0]

        partition_path = f"{device}p{part_num}" if "loop" in device else f"{device}{part_num}"

        # Format it
        if fs == 'f2fs':
            Format_cmd = f"mkfs.f2fs -f -l {label} {partition_path}"
        else:
            Format_cmd = f"mkfs.ext4 -L {label} {partition_path}"

        res = mgr.run_local(Format_cmd, sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to format partition {partition_path}: {res.stderr}")

def expand_partition(mgr: BaseImageManager, partition_number: int) -> None:
    """Expand a partition to fill all available space up to 100% of the device."""
    with target_block_device(mgr) as device:
        res = mgr.run_local(f"parted -s {device} resizepart {partition_number} 100%", sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to expand partition {partition_number}: {res.stderr}")

        mgr.run_local("udevadm settle", sudo=True)

        partition_path = f"{device}p{partition_number}" if "loop" in device else f"{device}{partition_number}"

        # Resize file system based on ext4
        res2 = mgr.run_local(f"e2fsck -f -y {partition_path}", sudo=True)
        # return code 1 from e2fsck means file system errors corrected, which is "success" for an auto-fix
        if res2.returnCode > 1:
            pass # We could log it

        res3 = mgr.run_local(f"resize2fs {partition_path}", sudo=True)
        if res3.returnCode != 0:
            raise RuntimeError(f"Failed to resize filesystem on {partition_path}: {res3.stderr}")

def remove_raspian_fs_resize(mgr: BaseImageManager) -> None:
    """Remove default Raspian auto-resize mechanisms directly in the target."""
    # This expects to be executed inside the chroot, so using standard mgr.run
    mgr.run("rm -f /etc/init.d/resize2fs_once", sudo=True)
    mgr.run("systemctl disable resize2fs_once || true", sudo=True)

    # Needs cmdline.txt modification, but the lib cmdline handles that
    pass

def inject_custom_resize(mgr: BaseImageManager, target_partition_num: int) -> None:
    """Overwrite the default RaspiOS init_resize.sh to target a different partition."""
    # Provide a simple bash script that does exactly what their init_resize.sh does,
    # but targeted at target_partition_num rather than ROOT_PART_NUM.
    custom_script = r'''#!/bin/sh
# Custom os-config resize script for partition {target_partition_num}
# Removed original RaspiOS root-expanding logic

reboot_pi () {{
  sleep 5
  reboot
}}

FAIL_REASON=""
TARGET_PART={target_partition_num}

if parted -s /dev/mmcblk0 resizepart $TARGET_PART 100%; then
  partprobe /dev/mmcblk0
  resize2fs /dev/mmcblk0p$TARGET_PART
else
  FAIL_REASON="Partition resize failed"
fi

if [ -z "$FAIL_REASON" ]; then
  # Remove init_resize.sh references from cmdline.txt here if possible
  sed -i 's/ init=\\/usr\\/lib\\/raspi-config\\/init_resize\\.sh//' /boot/cmdline.txt
  sed -i 's/ init=\\/usr\\/lib\\/raspi-config\\/init_resize\\.sh//' /boot/firmware/cmdline.txt
fi

reboot_pi
'''
    mgr.write_file("/usr/lib/raspi-config/init_resize.sh", custom_script, sudo=True)
    mgr.run("chmod +x /usr/lib/raspi-config/init_resize.sh", sudo=True)
