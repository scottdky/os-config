image_path=$1
mount_path=$2
root_partition=${3:-2} # default to 2
#echo $3

# dump the partition table, locate boot partition and root partition
boot_partition=1
fdisk_output=$(sfdisk -d $image_path)
boot_offset=$(($(echo "$fdisk_output" | grep "$image_path$boot_partition" | awk '{print $4-0}') * 512))
root_offset=$(($(echo "$fdisk_output" | grep "$image_path$root_partition" | awk '{print $4-0}') * 512))

echo "Mounting image $image_path on $mount_path, offset for boot partition is $boot_offset, offset for root partition is $root_offset"

# mount root and boot partition
sudo mount -o loop,offset=$root_offset $image_path $mount_path/
if [[ "$boot_partition" != "$root_partition" ]]; then
        sudo mount -o loop,offset=$boot_offset,sizelimit=$( expr $root_offset - $boot_offset ) $image_path $mount_path/boot
fi

# bind real /dev to our mounted img /dev
sudo mkdir -p $mount_path/dev/pts
sudo mount -o bind /dev $mount_path/dev
sudo mount -o bind /dev/pts $mount_path/dev/pts


