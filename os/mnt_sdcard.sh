#!/usr/bin/env bash

set -euo pipefail

device_path="$1"
mount_path="$2"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$script_dir/lib_mount_common.sh"

if [[ -z "$device_path" || -z "$mount_path" ]]; then
    echo "Usage: $0 <device_path> <mount_path>"
    exit 1
fi

if [[ ! -b "$device_path" ]]; then
    echo "Error: device is not a block device: $device_path"
    exit 1
fi

run_unmount_cleanup() {
    "$script_dir/unmnt_image.sh" "$mount_path" force 2>/dev/null || true
}

resolve_root_partition() {
    local rootPart=""
    rootPart="$(sudo lsblk -nrpo NAME,FSTYPE "$device_path" | awk '$2 == "ext4" {print $1; exit}')"
    echo "$rootPart"
}

resolve_boot_partition() {
    local bootPart=""
    bootPart="$(sudo lsblk -nrpo NAME,FSTYPE "$device_path" | awk '$2 ~ /^(vfat|fat16|fat32)$/ {print $1; exit}')"
    echo "$bootPart"
}

trap 'run_unmount_cleanup' ERR

require_command lsblk
require_command findmnt

root_partition="$(resolve_root_partition)"
if [[ -z "$root_partition" ]]; then
    echo "Could not find root partition (ext4) for device: $device_path"
    exit 1
fi

boot_partition="$(resolve_boot_partition)"

echo "Mounting SD card $device_path"
echo "Root partition: $root_partition"

prepare_mount_dirs "$mount_path"

sudo mount "$root_partition" "$mount_path"

if [[ -n "$boot_partition" && "$boot_partition" != "$root_partition" ]]; then
    echo "Boot partition: $boot_partition"
    if [[ -d "$mount_path/boot/firmware" ]]; then
        boot_mount_dir="$mount_path/boot/firmware"
    else
        boot_mount_dir="$mount_path/boot"
    fi
    sudo mount "$boot_partition" "$boot_mount_dir"
fi

bind_system_dirs "$mount_path"

if ! verify_mount_target "$mount_path" "Root"; then
    exit 1
fi

if [[ -n "$boot_partition" && "$boot_partition" != "$root_partition" ]]; then
    if ! verify_mount_target "$boot_mount_dir" "Boot"; then
        exit 1
    fi
fi

trap - ERR
