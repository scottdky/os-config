set -euo pipefail

image_path="$1"
mount_path="$2"
root_partition="${3:-2}" # default to 2
boot_partition="1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$image_path" ]]; then
        echo "Image file not found: $image_path"
        exit 1
fi

sudo mkdir -p "$mount_path" "$mount_path/boot" "$mount_path/dev" "$mount_path/dev/pts"

run_unmount_cleanup() {
        "$script_dir/unmnt_image.sh" "$mount_path" force 2>/dev/null || true
}

trap 'run_unmount_cleanup' ERR

# dump the partition table, locate boot partition and root partition
fdisk_output="$(sfdisk -d "$image_path")"

boot_start="$(echo "$fdisk_output" | awk -v part="$image_path$boot_partition" '$1==part {print $4-0}')"
root_start="$(echo "$fdisk_output" | awk -v part="$image_path$root_partition" '$1==part {print $4-0}')"

if [[ -z "$root_start" || "$root_start" == "0" ]]; then
        echo "Could not determine root partition offset for $image_path partition $root_partition"
        exit 1
fi

if [[ -z "$boot_start" || "$boot_start" == "0" ]]; then
        echo "Could not determine boot partition offset for $image_path partition $boot_partition"
        exit 1
fi

boot_offset="$((boot_start * 512))"
root_offset="$((root_start * 512))"

echo "Mounting image $image_path on $mount_path, offset for boot partition is $boot_offset, offset for root partition is $root_offset"

# mount root and boot partition
sudo mount -o "loop,offset=$root_offset" "$image_path" "$mount_path"

if [[ "$boot_partition" != "$root_partition" ]]; then
        size_limit="$((root_offset - boot_offset))"
        if [[ "$size_limit" -le 0 ]]; then
                echo "Invalid boot sizelimit computed ($size_limit)."
                run_unmount_cleanup
                exit 1
        fi
        sudo mount -o "loop,offset=$boot_offset,sizelimit=$size_limit" "$image_path" "$mount_path/boot"
fi

# bind real /dev to our mounted img /dev
sudo mount -o bind /dev "$mount_path/dev"
sudo mount -o bind /dev/pts "$mount_path/dev/pts"

# sanity checks to avoid partial mounts
if ! findmnt -T "$mount_path" >/dev/null 2>&1; then
        echo "Root mount verification failed for $mount_path"
        run_unmount_cleanup
        exit 1
fi

if [[ "$boot_partition" != "$root_partition" ]] && ! findmnt -T "$mount_path/boot" >/dev/null 2>&1; then
        echo "Boot mount verification failed for $mount_path/boot"
        run_unmount_cleanup
        exit 1
fi

trap - ERR


