"""Manager factory and interactive manager creation helpers."""

from .base import BaseManager, DEFAULT_MOUNT_PATH
from .image import ImageFileManager, SDCardManager
from .local import LocalManager
from .util import get_single_selection
from .remote import SSHManager


def create_manager(mode: str, **kwargs) -> BaseManager:
    """Factory function to create the appropriate manager for a mode."""
    mode = mode.lower()

    if mode == 'local':
        return LocalManager()
    if mode == 'ssh':
        return SSHManager(**kwargs)
    if mode == 'image':
        return ImageFileManager(**kwargs)
    if mode == 'sdcard':
        if kwargs.get('interactive'):
            kwargs.pop('interactive')
            return SDCardManager.from_interactive_selection(**kwargs)
        return SDCardManager(**kwargs)
    raise ValueError(f"Unknown mode: {mode}. Use 'local', 'ssh', 'image', or 'sdcard'")


def interactive_create_manager() -> BaseManager | None:
    """Interactively create a manager using terminal menus."""
    options = ["Local (localhost)", "SSH (Remote)", "Image File", "SD Card"]

    while True:
        selectedModeIdx = get_single_selection(options, title="Select Manager Mode")
        if selectedModeIdx is None:
            print("Exiting manager selection.")
            return None

        if selectedModeIdx == 0:
            return create_manager('local')

        if selectedModeIdx == 1:
            print("\n--- SSH Configuration ---")
            hostName = input("Hostname: ").strip()
            while not hostName:
                hostName = input("Hostname (required): ").strip()

            userName = input("Username (optional): ").strip() or None
            keyFilename = input("Key Filename (optional): ").strip() or None
            password = input("Password (optional): ").strip() or None

            return create_manager('ssh', hostName=hostName, userName=userName,
                                  keyFilename=keyFilename, password=password)

        if selectedModeIdx == 2:
            print("\n--- Image File Configuration ---")
            imagePath = input("Image File Path (required): ").strip()
            while not imagePath:
                imagePath = input("Image File Path (required): ").strip()

            mountPath = input(f"Mount Path [{DEFAULT_MOUNT_PATH}]: ").strip() or DEFAULT_MOUNT_PATH
            return create_manager('image', imagePath=imagePath, mountPath=mountPath)

        if selectedModeIdx == 3:
            print("\n--- SD Card Configuration ---")
            sdCardSelectionModeIdx = get_single_selection(
                ["Auto-detect USB devices", "Enter device path manually"],
                title="SD Card Selection",
                addExit="Back to main menu"
            )

            if sdCardSelectionModeIdx is None:
                continue

            if sdCardSelectionModeIdx == 0:
                manager = SDCardManager.from_interactive_selection(mountPath=DEFAULT_MOUNT_PATH)
                if manager is None:
                    continue
                return manager

            devicePath = input("Device Path (e.g., /dev/sdb): ").strip()
            while not devicePath:
                devicePath = input("Device Path (required): ").strip()

            mountPath = input(f"Mount Path [{DEFAULT_MOUNT_PATH}]: ").strip() or DEFAULT_MOUNT_PATH
            return create_manager('sdcard', devicePath=devicePath, mountPath=mountPath)


__all__ = ['create_manager', 'interactive_create_manager']
