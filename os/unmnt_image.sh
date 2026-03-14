set -euo pipefail

mount_path="$1"
force=""

if [ "$#" -gt 1 ]; then
    force="$2"
fi

if [ -z "$mount_path" ]; then
    echo "Usage: $0 <mount_path> [force]"
    exit 1
fi

if [ ! -d "$mount_path" ]; then
    echo "Error: mount path does not exist or is not a directory: $mount_path"
    exit 1
fi

if ! command -v findmnt >/dev/null 2>&1; then
    echo "Error: findmnt is required but not available on this system."
    exit 1
fi

if ! command -v losetup >/dev/null 2>&1; then
    echo "Error: losetup is required but not available on this system."
    exit 1
fi

# If force is specified, kill processes using the mount path before unmounting.
if [ -n "$force" ]; then
    processes=$(sudo lsof -t +D "$mount_path" 2>/dev/null | sort -u)
    for process in $processes; do
        echo "Killing process id $process..."
        sudo kill -9 "$process" 2>/dev/null || true
    done
fi

# Capture mount sources before unmount so we can detach loop devices after unmounting.
sources=$(sudo findmnt -R -r -n -o SOURCE --target "$mount_path" 2>/dev/null | awk 'NF' || true)
loop_devices=""
if [ -n "$sources" ]; then
    loop_devices=$(echo "$sources" | sed -nE 's#^(/dev/loop[0-9]+)(p[0-9]+)?$#\1#p' | sort -u)
fi

# Get mount targets under mount_path, deepest first.
targets=$(sudo findmnt -R -r -n -o TARGET --target "$mount_path" 2>/dev/null | awk 'NF' | sort -r)

oldIFS="$IFS"
IFS='
'

if [ -n "$targets" ]; then
    for target in $targets; do
        echo "Unmounting $target..."
        sudo umount "$target" 2>/dev/null || true
    done
fi

# Retry common bind mounts explicitly in case they were missed.
sudo umount "$mount_path/dev/pts" 2>/dev/null || true
sudo umount "$mount_path/dev" 2>/dev/null || true

# Detach any loop devices associated with mounted sources.
if [ -n "$loop_devices" ]; then
    for loop_device in $loop_devices; do
        echo "Detaching loop device $loop_device..."
        sudo losetup -d "$loop_device" 2>/dev/null || true
    done
fi

# Remove empty mount helper directories.
emptyDirs=$(sudo find "$mount_path" -mindepth 1 -depth -type d -empty 2>/dev/null || true)
if [ -n "$emptyDirs" ]; then
    for directoryPath in $emptyDirs; do
        sudo rmdir "$directoryPath" 2>/dev/null || true
    done
fi

sudo rmdir "$mount_path/dev/pts" 2>/dev/null || true
sudo rmdir "$mount_path/dev" 2>/dev/null || true
sudo rmdir "$mount_path" 2>/dev/null || true

IFS="$oldIFS"
