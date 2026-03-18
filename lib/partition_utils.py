"""
Utility functions for partition and filesystem management.
Requires `run_local()` available on the provided manager instance for host-side commands.
"""

import json
import logging
import re
from contextlib import contextmanager
from typing import Any, Generator

from lib.managers.image import BaseImageManager, ImageFileManager, SDCardManager

logger = logging.getLogger(__name__)

def _get_target_path(mgr: BaseImageManager) -> str:
    if isinstance(mgr, ImageFileManager):
        return mgr.imagePath
    elif isinstance(mgr, SDCardManager):
        return mgr.devicePath
    else:
        raise ValueError("Provided manager must be an ImageFileManager or SDCardManager")

@contextmanager
def target_block_device(mgr: BaseImageManager) -> Generator[str, None, None]:
    targetPath = _get_target_path(mgr)
    
    if isinstance(mgr, SDCardManager):
        yield targetPath
        return
        
    res = mgr.run_local(f"losetup -P -f --show {targetPath}", sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to attach image to loop device: {res.stderr}")
    
    loop_dev = res.stdout.strip()
    try:
        yield loop_dev
    finally:
        mgr.run_local(f"losetup -d {loop_dev}", sudo=True)

def expand_image_file(mgr: ImageFileManager, additional_mb: int) -> None:
    if not isinstance(mgr, ImageFileManager):
        return
    if additional_mb <= 0:
        return
        
    targetPath = _get_target_path(mgr)
    cmd = f"truncate -s +{additional_mb}M {targetPath}"
    res = mgr.run_local(cmd, sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to expand image file: {res.stderr}")

def get_partitions(mgr: BaseImageManager) -> list[dict[str, Any]]:
    with target_block_device(mgr) as device:
        cmd = f"lsblk -J -b -o NAME,SIZE,FSTYPE,LABEL,PARTLABEL,TYPE,MOUNTPOINT {device}"
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
    res = mgr.run_local(f"parted -sm {device} unit MB print free | tail -1", sudo=True)
    if res.returnCode != 0:
        raise RuntimeError(f"Failed to read parted print free: {res.stderr}")
    
    parts = res.stdout.strip().split(':')
    if len(parts) >= 4 and 'free' in res.stdout.lower():
        return {'start': parts[1], 'end': parts[2], 'size': parts[3]}
    return {}

def resolve_partition_num(mgr: BaseImageManager, identifier: dict) -> int:
    """Resolve partition number directly from identifier dict using 'partition_num', 'label' or 'mount'."""
    if 'partition_num' in identifier:
        return int(identifier['partition_num'])
        
    if 'mount' in identifier:
        mountpoint = identifier['mount']
        res = mgr.run(f"findmnt -n -o SOURCE {mountpoint}", sudo=True)
        if res.returnCode == 0 and res.stdout.strip():
            src_dev = res.stdout.strip()
            match = re.search(r'p?(\d+)$', src_dev)
            if match:
                return int(match.group(1))

    if 'label' in identifier:
        lbl = identifier['label']
        for p in get_partitions(mgr):
            if p.get('label') == lbl or p.get('partlabel') == lbl:
                match = re.search(r'p?(\d+)$', p.get('name', ''))
                if match:
                    return int(match.group(1))
                    
    raise ValueError(f"Could not resolve partition for {identifier}")

def is_last_partition(mgr: BaseImageManager, part_num: int) -> bool:
    """Checks if a given partition is physically the last one on the block device."""
    parts = get_partitions(mgr)
    nums = []
    for p in parts:
        name = p.get('name', '')
        match = re.search(r'p?(\d+)$', name)
        if match:
            nums.append(int(match.group(1)))
    if not nums:
        return False
    return part_num == max(nums)

def check_partition_exists(mgr: BaseImageManager, label: str) -> bool:
    for p in get_partitions(mgr):
        if p.get('label') == label or p.get('partlabel') == label:
            return True
    return False

def add_partition(mgr: BaseImageManager, label: str, size_mb: int = 0, fs: str = 'ext4') -> str:
    """Returns the new block device identifier (e.g. dev/loop0p3)"""
    with target_block_device(mgr) as device:
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
            
        mgr.run_local("udevadm settle", sudo=True)
        
        res = mgr.run_local(f"parted -sm {device} print | tail -1", sudo=True)
        part_num = res.stdout.strip().split(':')[0]
        partition_path = f"{device}p{part_num}" if "loop" in device else f"{device}{part_num}"

        if fs == 'f2fs':
            mgr.run_local(f"mkfs.f2fs -f -l {label} {partition_path}", sudo=True)
        else:
            mgr.run_local(f"mkfs.ext4 -F -L {label} {partition_path}", sudo=True)
            
        return partition_path

def expand_partition(mgr: BaseImageManager, partition_number: int, size_mb: int = 0) -> None:
    if size_mb == 0 and isinstance(mgr, ImageFileManager):
        raise RuntimeError("Full volume expansion for image files must be deferred to boot-time using inject_custom_resize.")

    with target_block_device(mgr) as device:
        if size_mb > 0:
            # Get current end size and add size_mb
            res = mgr.run_local(f"parted -sm {device} print", sudo=True)
            current_end = "0MB"
            for line in res.stdout.splitlines():
                if line.startswith(f"{partition_number}:"):
                    current_end = line.split(':')[2]
                    break
            
            end_num = float(current_end.replace('MB', '').replace('kB', ''))
            new_end = end_num + size_mb
            res = mgr.run_local(f"parted -s {device} resizepart {partition_number} {int(new_end)}MB", sudo=True)
        else:
            res = mgr.run_local(f"parted -s {device} resizepart {partition_number} 100%", sudo=True)
            
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to expand partition {partition_number}: {res.stderr}")
        
        mgr.run_local("udevadm settle", sudo=True)
        
        partition_path = f"{device}p{partition_number}" if "loop" in device else f"{device}{partition_number}"
        
        mgr.run_local(f"e2fsck -p -f {partition_path}", sudo=True)
        res3 = mgr.run_local(f"resize2fs {partition_path}", sudo=True)
        if res3.returnCode != 0:
            raise RuntimeError(f"Failed to resize filesystem on {partition_path}: {res3.stderr}")

def remove_raspian_fs_resize(mgr: BaseImageManager) -> None:
    mgr.run("rm -f /etc/init.d/resize2fs_once", sudo=True)
    mgr.run("systemctl disable resize2fs_once || true", sudo=True)

def inject_custom_resize(mgr: BaseImageManager, target_partition_num: int) -> None:
    custom_script = r'''#!/bin/sh
# Custom os-config resize script for partition TARGET_PART
reboot_pi () {
  sleep 5
  reboot
}

parted -s /dev/mmcblk0 resizepart TARGET_PART 100%
partprobe /dev/mmcblk0
resize2fs /dev/mmcblk0pTARGET_PART

sed -i 's/ init=\/usr\/lib\/raspi-config\/init_resize\.sh//' /boot/cmdline.txt
sed -i 's/ init=\/usr\/lib\/raspi-config\/init_resize\.sh//' /boot/firmware/cmdline.txt
reboot_pi
'''.replace("TARGET_PART", str(target_partition_num))

    mgr.write_file("/usr/lib/raspi-config/init_resize.sh", custom_script, sudo=True)
    mgr.run("chmod +x /usr/lib/raspi-config/init_resize.sh", sudo=True)
