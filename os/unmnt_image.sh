mount_path=$1
force=
if [ "$#" -gt 1 ]
then
force=$2
fi

if [ -n "$force" ]
then
for process in $(sudo lsof $mount_path | awk '{print $2}')
do
    echo "Killing process id $process..."
    sudo kill -9 $process
done
fi

# Unmount everything that is mounted
# 
# We might have "broken" mounts in the mix that point at a deleted image (in case of some odd
# build errors). So our "sudo mount" output can look like this:
#
#     /path/to/our/image.img (deleted) on /path/to/our/mount type ext4 (rw)
#     /path/to/our/image.img on /path/to/our/mount type ext4 (rw)
#     /path/to/our/image.img on /path/to/our/mount/boot type vfat (rw)
#
# so we split on "on" first, then do a whitespace split to get the actual mounted directory.
# Also we sort in reverse to get the deepest mounts first.
for m in $(sudo mount | grep $mount_path | awk -F "on" '{print $2}' | awk '{print $1}' | sort -r)
do
echo "Unmounting $m..."
sudo umount $m
done
