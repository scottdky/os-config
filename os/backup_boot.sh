#!/bin/sh

# This script is to run from initramfs. It checks to see if USB fs is present. If so,
# it boots from it, else falls back to sd card.

# To setup sdcard & usb drive:
# 1) Install desired OS to each drive
# 2) On sd card, copy /boot/cmdline.txt to /boot/cmdline_sd.txt
# 3) On USB drive, modify /boot/cmdline.txt to 'root=/dev/sda2'

# To install this script:
# 1) Copy to /etc/initramfs-tools/local-premount
# 2) Mark it executable: $ sudo chmod +x /etc/initramfs-tools/local-premount/backup_boot.sh
# 3) Boot up Pi via sd card
# 3) Update the initramfs image:  $ update-initramfs -u

# Now test booting with USB drive inserted and again without it

# Refs:
# The original idea - https://rlogiacco.wordpress.com/2014/08/04/xbian-from-usb-with-sd-fallback/
# The debian boot process - https://wiki.debian.org/BootProcess
# Writing a pre-mount script - https://unix.stackexchange.com/questions/87814/how-to-write-a-pre-mount-startup-script
# Updating initramfs image - http://manpages.ubuntu.com/manpages/precise/man8/update-initramfs.8.html
# Docs for initramfs scripts (good info) - https://manpages.debian.org/jessie/initramfs-tools/initramfs-tools.8.en.html


mkdir /mnt/sd_boot
/bin/mount /dev/mmcblk0p1 /mnt/sd_boot
mkdir /mnt/usb_boot
/bin/mount /dev/sda1 /mnt/usb_boot
if [ $? -eq 0]; then # usb mount succeeded
    cp /mnt/usb_boot/cmdline.txt /mnt/sd_boot/cmdline.txt
    umount /mnt/usb_boot
else # usb mount failed
    cp /mnt/sd_boot/cmdline_sd.txt /mnt/sd_boot/cmdline.txt
fi

umount /mnt/sd_boot
