# This script will expand the FS (for Raspberry Pi) to fill the SD card/USB drive

# Usage: expanddiskfs.sh DEVICE
# Ex:   expanddiskfs.sh /dev/sdb
#
device=$1
partion=2

# Operation explained:
# Each line of dochere is a response to the interactive fdisk cmd:
# p (1st one) - print the partition table
# d - delete a partition, followed by the partition number
# n - create a new partition, followed by p to select a primary partition, followed the start of the partition,
#     followed by the size of the partition (<CR> defaults to the entire disk, hence the blank line)
# p - print the new table
# w - write it to disk (actually implement the changes)

echo "Expanding FS on $device..."
start=$(sudo sfdisk -d $device | grep "$device2" | awk '{print $4-0}')
sudo fdisk $device <<FDISK
p
d
$partition
n
p
$partition
$start

p
w
FDISK
echo "Resized FS (parition 2) of $device to fill disk"
