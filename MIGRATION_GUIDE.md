# Migration Guide: Fabric 1.x to cmd_manager

This guide helps migrate Fabric-style workflows to the current `cmd_manager` API.

## Current Supported Modes

`create_manager()` supports these modes:

- `local`
- `ssh`
- `image`
- `sdcard`

The old `chroot` mode is no longer supported.

## Key Differences

### Fabric 1.x Pattern
```python
from fabric.api import run, sudo, put, env

env.host_string = 'user@hostname'
env.key_filename = '/path/to/key'

run('ls -la')
sudo('apt-get update')
put('/local/file', '/remote/file')
```

### cmd_manager Pattern
```python
from lib.cmd_manager import create_manager

with create_manager(
    'ssh',
    hostName='hostname',
    userName='user',
    keyFilename='/path/to/key'
) as mgr:
    mgr.run('ls -la')
    mgr.run('apt-get update', sudo=True)
    mgr.put('/local/file', '/remote/file')
```

## Mode Selection Migration

### Before
```python
if location == 'local':
    env.host_string = 'localhost'
elif location == 'remote':
    env.host_string = 'pi@192.168.1.100'
elif location == 'chroot':
    mountImage('/path/to/raspi.img')
    runAsChroot('apt-get update')
```

### After
```python
from lib.cmd_manager import create_manager

if location == 'local':
    mgr = create_manager('local')
elif location == 'ssh':
    mgr = create_manager('ssh', hostName='192.168.1.100', userName='pi')
elif location == 'image':
    mgr = create_manager('image', imagePath='/path/to/raspi.img')
elif location == 'sdcard':
    mgr = create_manager('sdcard', devicePath='/dev/sdb')
else:
    raise ValueError(f'Unsupported location: {location}')

with mgr:
    mgr.run('apt-get update', sudo=True)
```

## Complete Migration Example

```python
from lib.cmd_manager import create_manager


def setup_system(target: str, remoteHost: str | None = None,
                 imagePath: str | None = None, devicePath: str | None = None) -> None:
    if target == 'local':
        mgr = create_manager('local')
    elif target == 'ssh':
        mgr = create_manager(
            'ssh',
            hostName=remoteHost or '192.168.1.100',
            userName='pi',
            keyFilename='/home/user/.ssh/id_rsa'
        )
    elif target == 'image':
        if not imagePath:
            raise ValueError('imagePath required for image target')
        mgr = create_manager('image', imagePath=imagePath)
    elif target == 'sdcard':
        if not devicePath:
            raise ValueError('devicePath required for sdcard target')
        mgr = create_manager('sdcard', devicePath=devicePath)
    else:
        raise ValueError(f'Unknown target: {target}')

    with mgr:
        mgr.run('apt-get update', sudo=True)
        mgr.run('apt-get install -y vim', sudo=True)
        mgr.put('/local/bashrc', '/root/.bashrc', sudo=True)
```

## Fabric Function Mapping

| Fabric 1.x | cmd_manager |
|------------|-------------|
| `run('command')` | `mgr.run('command')` |
| `sudo('command')` | `mgr.run('command', sudo=True)` |
| `put('/local', '/remote')` | `mgr.put('/local', '/remote')` |
| `put('/local', '/remote', use_sudo=True)` | `mgr.put('/local', '/remote', sudo=True)` |
| `exists('/path')` | `mgr.exists('/path')` |

## Image and SD Card Usage

### Image file workflow
```python
from lib.cmd_manager import create_manager

with create_manager('image', imagePath='/path/to/raspios.img') as mgr:
    mgr.run('apt-get update', sudo=True)
    mgr.run('uname -a')
    mgr.put('/local/file', '/etc/config')
```

### SD card workflow
```python
from lib.cmd_manager import create_manager

with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
    mgr.run('hostname')
    mgr.put('/local/hosts', '/etc/hosts', sudo=True)
```

### Interactive SD selection
```python
from lib.cmd_manager import create_manager

mgr = create_manager('sdcard', interactive=True)
if mgr is not None:
    with mgr:
        mgr.run('hostname')
```

## Mount Behavior and Parameters

For `image` and `sdcard` managers:

- mounting happens automatically on manager creation
- existing mounts are reused when detected
- unmount happens on `close()` / context manager exit unless `keepMounted=True`

Common parameters:

- `mountPath` (default `/mnt/image`)
- `forceUnmount` (force cleanup on unmount)
- `keepMounted` (skip automatic unmount)
- `defaultChrootUser` (non-root chroot user when `sudo=False`)

Target-specific parameters:

- `image`: `imagePath='/path/to/file.img'`
- `sdcard`: `devicePath='/dev/sdX'` or `interactive=True`

## Migration Tips

1. Pass manager objects into functions instead of relying on global Fabric env state.
2. Prefer context managers (`with`) for reliable cleanup.
3. Replace any `create_manager('chroot', ...)` calls with explicit `image` or `sdcard` mode.
4. Keep naming consistent with live kwargs (`mountPath`, `forceUnmount`, `keepMounted`).
5. Test each target mode (`local`, `ssh`, `image`, `sdcard`) independently after migration.

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
