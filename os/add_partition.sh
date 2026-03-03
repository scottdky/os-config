#!/bin/bash
# This script will add a partition to a Raspbian SD card and format it.
# NB - it only works on devices; not images

# Pars:
#   Device - /dev root file, e.g. /dev/sdb
#   Size - size in MB of the partition. Use 0 to fill disk
#   FS (filesystem) - the name of the filesystem to format it to, e.g. ext4, f2fs2
#   Label - the label for the partition
#
# Usage: add_data_partition.sh DEVICE SIZE(MB) FS LABEL
# Ex:   add_data_partition /dev/sdb 500 f2fs home
#
# The point of the partition is when setting up a readonly
# or overlay fs and you want another partition with write access.
#
#    Some interesting discussions on the merits of f2fs vs ext4:
#    https://forum.manjaro.org/t/why-not-install-under-f2fs-instead-of-ext4/124416/18
#    https://www.raspberrypi.org/forums/viewtopic.php?t=227928
#


device=$1
size=$2
fs=$3
label=$4

echo "Adding $size MB partition on $device, labeled $label with FS $fs..."

# get info on the free space
line=$(parted -sm $device unit MB print free | tail -1)
# line ex.:  1:15.0GB:31.9GB:16.9GB:free;
start=$(echo $line | awk -F: '{print $2}')
# end of disk
end=$(echo $line | awk -F: '{print $3}')
# figure out stop for partition
if [ "$size" = "0" ]; then
    stop=$end
else
    stop=$((${start:0:-2} + $size))'MB'
fi
# create partition
parted -s $device mkpart primary $start $stop
echo "created new partition..."

# now format it
lastPart=$(parted -sm $device print | tail -1)
partNum=${lastPart:0:1}
if [ "$fs" = "f2fs" ]; then
    echo "formating partition to f2fs..."
    apt install -y f2fs-tools # make sure f2fs is installed
    mkfs.f2fs -l "$label" "${device}$partNum" # format partition as f2fs
else # ext4
    echo "formating partition to ext4..."
    mkfs.ext4 -l "$label" "${device}$partNum" # format partition as ext4
fi

echo "Done creating partition."
