#!/bin/bash

# Given the path to a mounted ARM image FS, and a script to execute on that image, execute it via chroot with ARM emulation
# Pars: $1 - path to the mounted FS; $2 - bash script to execute on that FS

# NOTE: requires installation of qemu-user on host system

root_path=$1
#script=$2

# test to see if script ($2) is a file
#script="$PWD/$2"
script=$2
echo "script: $script"

cd $root_path # cd into our image fs, ie /

#black magic of qemu-arm-static - copy it into the image fs (note it is usr/bin, not /usr/bin
# use rsync instead of cp; that way, this script can be called multiple times without performance penalty
rsync -aq $(which qemu-arm-static) usr/bin/

# copy our script onto the FS so it is available when we chroot
if [ -f $script ]; then    
    cp $script chroot_script
else
    echo $2 > chroot_script   # if not a script, then make a script - chroot doesn't accept cmds
    echo 'chroot_script: '
    cat chroot_script
fi
chmod 755 chroot_script

# here is where it all happens:
# chroot onto the image's fs, using genu-arm-static emulation, and then execute the script via bash
# Unfortunately, we can only execute a single script at a time; if we don't provide the script, then this script
# immediately exits into our current shell, which is now chroot. It must be exited by typing 'exit' at which point
# this script resumes. Granted, it is pretty cool, but not what we want.
chroot . usr/bin/qemu-arm-static bin/bash /chroot_script

#cleanup
rm chroot_script

echo 'exiting chroot.sh'
