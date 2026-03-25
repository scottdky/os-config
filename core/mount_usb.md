# USB Mount Helper Logic

When your application needs to locate actively mounted USB drives, it should handle both the modern `systemd-mount` paths as well as the legacy `usb_automount.sh` structure to maintain backwards compatibility with existing systems.

The following Python snippet demonstrates how to safely grab live mount points combining both paradigms:

```python
import os
import glob

def get_usb_drives() -> list[str]:
    """
    Dynamically locate active USB drive mount points.

    Returns:
        list[str]: Absolute paths to actively mounted USB drives.
    """
    # Modern paths injected by systemd-mount transient units
    modernPaths = glob.glob('/run/media/sd[a-z][0-9]*')

    # Legacy paths traditionally used by bash-based scripts
    legacyPaths = glob.glob('/media/usb*')

    potentialMounts = modernPaths + legacyPaths

    # Filter: strictly verify the OS has successfully bound a filesystem to the directory
    activeMounts = [path for path in potentialMounts if os.path.ismount(path)]

    return activeMounts
```
