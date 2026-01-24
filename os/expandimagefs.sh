
# call like this: enlarge_ext /path/to/image partition size
#
# will enlarge partition number <partition> on /path/to/image by <size> MB
image=$1
partition=$2
size=$3


echo "Adding $size MB to partition $partition of $image"
start=$(sfdisk -d $image | grep "$image$partition" | awk '{print $4-0}')
offset=$(($start*512))
sudo dd if=/dev/zero bs=1M count=$size >> $image
sudo fdisk $image <<FDISK
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

LODEV=$(losetup -f --show -o $offset $image)
trap 'sudo losetup -d $LODEV' EXIT

sudo e2fsck -fy $LODEV
sudo resize2fs -p $LODEV
sudo losetup -d $LODEV

trap - EXIT
echo "Resized parition $partition of $image to +$size MB"
