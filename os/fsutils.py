import os

from fabric.api import *
from fabric.contrib.files import *

"""
README
A set of file system utilities for working on os images


Usage:
To run one function:
fab -f fsutils.py func:arg

Or import this library into another fab file

"""

IMG_MOUNT_PATH = '/mnt/image'
#CWD = os.path.dirname(env.real_fabfile)
CWD = os.path.dirname(__file__)

def hackForChroot():
    """ In order for chroot to run apt update and similar os cmds, we need to implement this hack.
    It should be undone when finished.
    Ref:
    To fix this error when trying apt-update & similar - https://hblok.net/blog/posts/2014/02/06/chroot-to-arm/
        Comment out any lines in /mnt/image/etc/ld.so.preload
    Why - https://www.raspberrypi.org/forums/viewtopic.php?f=31&t=8478
    """
    sudo('mv {}/etc/ld.so.preload {}/etc/ld.so.preload.bck'.format(IMG_MOUNT_PATH, IMG_MOUNT_PATH))

def undoHackForChroot():
    """See hackForChroot. This undoes the change."""
    sudo('mv {}/etc/ld.so.preload.bck {}/etc/ld.so.preload'.format(IMG_MOUNT_PATH, IMG_MOUNT_PATH))
    

def basicRunScript(scriptFile, args = None, useSudo = False):
    """
    Given a filename for a bash script, run it. (Sometimes it is easier to code in bash or reuse other bash libraries).
    Pars:
        scriptFile: local file path for the bash script (doesn't need to be executable)
        args: args to pass to bash script (optional)
        useSudo: true if sudo should be used to run the script
    """
    if not args:
        with open(scriptFile) as f:
            script = f.read()
    else:
        #put(scriptFile, '/tmp/'+scriptFile, mode=0755)
        #script = '/tmp/{} {}'.format(script, args)
        script = '{} {}'.format(scriptFile, args)
        
    if useSudo:
        print 'script: {}'.format(script)
        sudo(script)
    else:
        run(script)

def runScript(scriptFile, *args, **kwargs):
    "Calls basicRunScript with all scripts located in bashscripts subdir. Args are passed as parameters. useSudo must be passed as kwarg."
    "The useSudo default is True. Ex: runScript('myscript.sh', PATH, myFile, useSudo=False)"
    if 'useSudo' in kwargs:
        useSudo = kwargs['useSudo']
    else:
        useSudo = True
    basicRunScript(os.path.join(CWD, 'bashscripts', scriptFile), ' '.join(args), useSudo)
    
    

def expandImageFS(imageFile, partition, size):
    print 'pars: {} {} {}'.format(imageFile, partition, size)    
    "Expand the given partition number on the image by size (MB)"
    runScript(os.path.join(CWD, 'bashscripts/expandimagefs.sh'), '{} {} {}'.format(imageFile, partition, size), useSudo=True)
        
def expandDiskFS(device):
    "Expand the FS on the device to fill the device"
    runScript(os.path.join(CWD, 'bashscripts/expanddiskfs.sh'), '{}'.format(device), useSudo=True)
    
def mkDir(dir):
    "Make dir on remote system. Return False if it already exists"
    with settings(warn_only=True):
        result=sudo('mkdir %s' % dir)
        if result.failed:
            print "%s dir already exists" % dir
            return False
    return True

def rmDir(dir):
    sudo('rmdir %s' % dir)
    

def mountImage(imageFile):
    """Mount an image file using the magic of Linux"""
    
    success = mkDir(IMG_MOUNT_PATH)
    if success:
        with settings(warn_only=True):
            runScript('mnt_image.sh', imageFile, IMG_MOUNT_PATH)
            # run hack so we can use chroot
            hackForChroot() # do in order to run apt cmds
    else:
        print "mount dir exists - skipping mounting"

def mountDrive(device):
    "Mount a flash drive where 1st partition is '/' (root), and the 2nd is '/boot'. Par device is root drive, e.g. /dev/sdb"

    success = mkDir(IMG_MOUNT_PATH)
    if success:
        with settings(warn_only=True):
            sudo('mount {} {}'.format(device+str(2), IMG_MOUNT_PATH))
            sudo('mount {} {}'.format(device+str(1), IMG_MOUNT_PATH+'/boot'))
            # run hack so we can use chroot
            hackForChroot() # do in order to run apt cmds
    else:
        print "mount dir exists - skipping mounting"

def unmountOS():
    "Unmount either an image or flash drive - they are both mounted the same"
    print 'unmounting os...'
    # reverse our hack for chroot
    with settings(warn_only=True):
        undoHackForChroot() # do in order to run apt cmds
    runScript('unmnt_image.sh', IMG_MOUNT_PATH)
    rmDir(IMG_MOUNT_PATH)
    print 'OS unmounted.'
        

def runAsChroot(script):
    """Run the given script as chroot. 'script' can be either the name of a script in 
    the folder bashscripts or it can be an actual bash command host_string
    """
    # if we are not local host, then run directly on the pi - chroot is not needed
    if env.host_string != 'localhost':
        # check to see if it is a file. If so read it in
        fname = os.path.join(CWD,'bashscripts',script)
        if os.path.isfile(fname):
            with open(fname) as f:
                script = f.read()
        sudo(script) # run it
    else: # run as chroot
        if not os.path.isfile(os.path.join(CWD,'bashscripts',script)):
            # put the cmd in a file
            fname = os.path.join(IMG_MOUNT_PATH, 'tmp', 'chrootcmdscript.sh') 
            run('echo "{}" > {}'.format(script, fname))
            runScript('chroot.sh', IMG_MOUNT_PATH, fname)
        else:
            runScript('chroot.sh', IMG_MOUNT_PATH, os.path.join(CWD,'bashscripts',script))
        
    
def testChroot(imageFile):
    mountImage(imageFile)
    runScript('chroot.sh', IMG_MOUNT_PATH, 'ls')
    runScript('chroot.sh', IMG_MOUNT_PATH, "'uname -a'")
    unmountImage()

