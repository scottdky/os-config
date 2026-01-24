# Migration Guide: Fabric 1.x to cmd_manager

This guide helps you migrate from Fabric 1.x to the new `cmd_manager` multi-location OS manager.

## Key Differences

### Fabric 1.x Pattern
```python
from fabric.api import run, sudo, put, settings, env

# Set target host
env.host_string = 'user@hostname'
env.key_filename = '/path/to/key'

# Execute commands
run('ls -la')
sudo('apt-get update')
put('/local/file', '/remote/file')
```

### cmd_manager Pattern
```python
from cmd_manager import create_manager

# Create manager for target
with create_manager('ssh', hostName='hostname', userName='user',
                    keyFilename='/path/to/key') as mgr:
    mgr.run('ls -la')
    mgr.run('apt-get update', sudo=True)
    mgr.put('/local/file', '/remote/file')
```

## Location Selection

### Old Fabric Way (with fsutils.py pattern)
```python
from fabric.api import env, run, sudo

# User selects location by setting env.host_string
if location == 'local':
    env.host_string = 'localhost'
elif location == 'remote':
    env.host_string = 'pi@192.168.1.100'
elif location == 'chroot':
    env.host_string = 'localhost'  # Then use runAsChroot()

# Different code paths for different locations
if location == 'chroot':
    runAsChroot('apt-get update')
else:
    sudo('apt-get update')
```

### New cmd_manager Way
```python
from cmd_manager import create_manager

# User selects location by choosing mode
if location == 'local':
    mgr = create_manager('local')
elif location == 'remote':
    mgr = create_manager('ssh', hostName='192.168.1.100', userName='pi')
elif location == 'chroot':
    mgr = create_manager('chroot', mount_path='/mnt/image')

# Same code for all locations!
mgr.run('apt-get update', sudo=True)
mgr.close()  # or use with context manager
```

## Complete Migration Example

### Before (Fabric 1.x with fsutils.py)
```python
from fabric.api import run, sudo, put, env
from fsutils import runAsChroot, mountImage, unmountImage

def setup_system(image_location, target):
    """
    Setup system on local, remote, or mounted image.
    target: 'local', 'remote', or 'chroot'
    """
    if target == 'local':
        env.host_string = 'localhost'
    elif target == 'remote':
        env.host_string = 'pi@192.168.1.100'
        env.key_filename = '/home/user/.ssh/id_rsa'
    elif target == 'chroot':
        env.host_string = 'localhost'
        mountImage(image_location)

    # Different execution paths
    if target == 'chroot':
        runAsChroot('apt-get update')
        runAsChroot('apt-get install -y vim')
        # File operations need different handling
        put('/local/bashrc', '/mnt/image/root/.bashrc')
    else:
        sudo('apt-get update')
        sudo('apt-get install -y vim')
        put('/local/bashrc', '/root/.bashrc', use_sudo=True)

    if target == 'chroot':
        unmountImage()
```

### After (cmd_manager)
```python
from cmd_manager import create_manager

def setup_system(image_location, target, remote_host=None):
    """
    Setup system on local, remote, or mounted image.
    target: 'local', 'ssh', or 'chroot'
    """
    # Create appropriate manager
    if target == 'local':
        mgr = create_manager('local')
    elif target == 'ssh':
        mgr = create_manager('ssh', hostName=remote_host or '192.168.1.100',
                           userName='pi', keyFilename='/home/user/.ssh/id_rsa')
    elif target == 'chroot':
        # Assumes image already mounted at /mnt/image
        mgr = create_manager('chroot', mountPath='/mnt/image')

    with mgr:
        # Same code for all targets!
        mgr.run('apt-get update', sudo=True)
        mgr.run('apt-get install -y vim', sudo=True)
        mgr.put('/local/bashrc', '/root/.bashrc', sudo=True)
```

## Function Parameter Migration

### Accepting Manager Instead of Using Global env

**Before:**
```python
from fabric.api import run, sudo, put

def install_packages():
    """Install packages on whatever host is set in env"""
    sudo('apt-get update')
    sudo('apt-get install -y vim htop')
```

**After:**
```python
def install_packages(mgr):
    """Install packages using provided manager"""
    mgr.run('apt-get update', sudo=True)
    mgr.run('apt-get install -y vim htop', sudo=True)

# Usage:
with create_manager('local') as mgr:
    install_packages(mgr)
```

## Common Fabric Functions Mapping

| Fabric 1.x | cmd_manager |
|------------|-------------|
| `run('command')` | `mgr.run('command')` |
| `sudo('command')` | `mgr.run('command', sudo=True)` |
| `put('/local', '/remote')` | `mgr.put('/local', '/remote')` |
| `put('/local', '/remote', use_sudo=True)` | `mgr.put('/local', '/remote', sudo=True)` |
| `append('/file', 'text')` | `mgr.append('/file', 'text')` |
| `exists('/path')` | `mgr.exists('/path')` |

## Chroot-Specific Migration

### Before (fsutils.py pattern)
```python
from fabric.api import env, run
from fsutils import mountImage, unmountImage, runAsChroot

# Mount the image
mountImage('/path/to/raspi.img')

# Execute commands
runAsChroot('apt-get update')
runAsChroot('uname -a')

# File operations on mounted filesystem
put('/local/file', '/mnt/image/etc/config')

# Cleanup
unmountImage()
```

### After (cmd_manager with auto-mount)
```python
from cmd_manager import create_manager

# Auto-mount handles everything!
with create_manager('chroot', autoMount=True,
                   imagePath='/path/to/raspi.img') as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.run('uname -a')

    # File operations work transparently
    mgr.put('/local/file', '/etc/config')  # Automatically goes to /mnt/image/etc/config

# Auto-unmount happens automatically

```

### After (cmd_manager - manual mount, legacy)
```python
from cmd_manager import create_manager

# Assumes image already mounted at /mnt/image
# (Use your existing mount scripts separately)

with create_manager('chroot', mountPath='/mnt/image') as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.run('uname -a')

    # File operations work transparently
    mgr.put('/local/file', '/etc/config')  # Automatically goes to /mnt/image/etc/config

# Unmount separately if needed
```

## Auto-Mount Features (New in cmd_manager)

### Image File Auto-Mount
```python
# Automatically mount, work, and unmount a Raspberry Pi image
with create_manager('chroot', autoMount=True,
                   imagePath='/path/to/raspios.img') as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.run('apt-get install -y vim', sudo=True)
# Image is automatically unmounted here
```

### SD Card Auto-Mount
```python
# Same interface works with SD cards (block devices)
with create_manager('chroot', autoMount=True,
                   imagePath='/dev/sdb') as mgr:
    mgr.run('hostname')
    mgr.append('/etc/hosts', '192.168.1.50 mydevice')
# SD card is automatically unmounted here
```

### Development Workflow (Keep Mounted)
```python
# Keep image mounted between operations
with create_manager('chroot', autoMount=True,
                   imagePath='/path/to/raspios.img',
                   keepMounted=True) as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.put('/local/config.txt', '/etc/myapp/config.txt')
# Image stays mounted

# Continue working later (manual mount mode)
with create_manager('chroot', mountPath='/mnt/image') as mgr:
    mgr.run('systemctl enable myservice', sudo=True)
# Still mounted

# When completely done, unmount manually or use auto_mount without keep_mounted
```

### Custom Mount Path
```python
# Mount to a custom location
with create_manager('chroot', auto_mount=True,
                   image_path='/path/to/raspios.img',
                   mount_path='/mnt/my_custom_mount') as mgr:
    mgr.run('ls -la /')
```

### Force Unmount (For Stuck Mounts)
```python
# Force-kill processes using the mount before unmounting
with create_manager('chroot', auto_mount=True,
                   image_path='/path/to/raspios.img',
                   force_unmount=True) as mgr:
    mgr.run('some command')
# Will force unmount even if processes are using it
```

### Skip Mounting if Already Mounted
```python
# Auto-mount automatically detects if image is already mounted
# and skips mounting - safe to call multiple times

with create_manager('chroot', auto_mount=True,
                   image_path='/path/to/raspios.img') as mgr:
    mgr.run('first operation')

# If image is still mounted from previous operation:
with create_manager('chroot', auto_mount=True,
                   image_path='/path/to/raspios.img') as mgr:
    # Detects existing mount, skips mounting
    mgr.run('second operation')
```

## Tips for Migration

1. **Create a wrapper function** for your location selection logic:
   ```python
   def get_manager(location_type, **kwargs):
       """Central function to create managers based on your app's logic"""
       if location_type == 'local':
           return create_manager('local')
       elif location_type == 'remote':
           return create_manager('ssh', **kwargs)
       elif location_type == 'mounted_image':
           return create_manager('chroot', mount_path=kwargs.get('mount_path', '/mnt/image'))
   ```

2. **Update functions to accept manager parameter** instead of relying on global env

3. **Use context managers** (`with` statement) to ensure proper cleanup

4. **Mount/unmount separately** for chroot - cmd_manager assumes the filesystem is already mounted

5. **Test each location type** independently to ensure commands work correctly

## Prerequisites

- **SSH mode**: Requires `paramiko` package (`pip install paramiko`)
- **Chroot mode**: Requires `qemu-user-static` package (`apt-get install qemu-user-static`)
- **Chroot mode (manual mount)**: Image must be mounted before creating ImageManager
- **Chroot mode (auto-mount)**: Bash scripts in `os/` directory must be present (mnt_image.sh, unmnt_image.sh)

## Troubleshooting

### "qemu-arm-static not found"
```bash
sudo apt-get install qemu-user-static
```

### "Mount path does not exist" warning
Mount your image first:
```bash
sudo mkdir /mnt/image
sudo mount -o loop,offset=... /path/to/image.img /mnt/image
```

### Commands fail in chroot
Ensure QEMU setup is correct. ImageManager automatically copies qemu-arm-static, but verify:
```bash
ls /mnt/image/usr/bin/qemu-arm-static
```

### Permission errors with sudo
- For LocalManager and ImageManager: Ensure your user has sudo privileges
- For SSHManager: Ensure remote user has sudo privileges and NOPASSWD is set if needed
