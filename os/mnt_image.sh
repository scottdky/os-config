#!/usr/bin/env bash

set -euo pipefail

image_path="$1"
mount_path="$2"
root_partition="${3:-2}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$script_dir/lib_mount_common.sh"

if [[ -z "$image_path" || -z "$mount_path" ]]; then
        echo "Usage: $0 <image_path> <mount_path> [root_partition_number]"
        exit 1
fi

if [[ ! -f "$image_path" ]]; then
        echo "Image file not found: $image_path"
        exit 1
fi

run_unmount_cleanup() {
        "$script_dir/unmnt_image.sh" "$mount_path" force 2>/dev/null || true
}

resolve_partition_path() {
        local loopDev="$1"
        local partitionNumber="$2"
        local withP="${loopDev}p${partitionNumber}"
        local withoutP="${loopDev}${partitionNumber}"

        if [[ -b "$withP" ]]; then
                echo "$withP"
                return 0
        fi
        if [[ -b "$withoutP" ]]; then
                echo "$withoutP"
                return 0
        fi
        return 1
}

find_boot_partition() {
        local loopDev="$1"
        local bootCandidate=""

        bootCandidate="$(lsblk -nrpo NAME,FSTYPE "$loopDev" | awk '$2 ~ /^(vfat|fat16|fat32)$/ {print $1; exit}')"
        echo "$bootCandidate"
}

trap 'run_unmount_cleanup' ERR

require_command findmnt
require_command losetup
require_command lsblk

prepare_mount_dirs "$mount_path"

loop_dev="$(sudo losetup -f --show -P "$image_path")"
if [[ -z "$loop_dev" ]]; then
        echo "Failed to attach loop device for image: $image_path"
        exit 1
fi

root_partition_path="$(resolve_partition_path "$loop_dev" "$root_partition" || true)"
if [[ -z "$root_partition_path" ]]; then
        echo "Could not determine root partition path for loop device $loop_dev partition $root_partition"
        exit 1
fi

boot_partition_path="$(find_boot_partition "$loop_dev")"

echo "Mounting image $image_path using loop device $loop_dev"
echo "Root partition: $root_partition_path"

sudo mount "$root_partition_path" "$mount_path"

if [[ -n "$boot_partition_path" && "$boot_partition_path" != "$root_partition_path" ]]; then
        echo "Boot partition: $boot_partition_path"
        sudo mount "$boot_partition_path" "$mount_path/boot"
fi

bind_system_dirs "$mount_path"

if ! verify_mount_target "$mount_path" "Root"; then
        exit 1
fi

if [[ -n "$boot_partition_path" && "$boot_partition_path" != "$root_partition_path" ]]; then
        if ! verify_mount_target "$mount_path/boot" "Boot"; then
                exit 1
        fi
fi

trap - ERR


