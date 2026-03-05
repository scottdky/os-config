#!/usr/bin/env python3
"""Interactive debugger entrypoint for image/SD-card mount flow step-through."""

from lib.managers import BaseImageManager, interactive_create_manager


def main() -> None:
    """Launch interactive manager selection and hold lifecycle in a context block."""
    manager = interactive_create_manager()
    if manager is None:
        print("No manager selected.")
        return

    if isinstance(manager, BaseImageManager):
        manager.keepMounted = True
        print("Debug mode: keepMounted=True")

    print(f"Created manager: {type(manager).__name__}")

    try:
        with manager:
            print("Manager context entered.")
            # Keep a simple command here so both mount and run paths are debuggable.
            result = manager.run('ls -la /home | head -n 20')
            print(f"Command exit code: {result.returnCode}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
    finally:
        if isinstance(manager, BaseImageManager):
            response = input("Keep mounted? [Y/n]: ").strip().lower()
            if response in ('n', 'no'):
                manager.keepMounted = False
                manager.close()
                print("Unmount requested and completed.")
            else:
                print("Leaving mounts active for debugging.")
        print("Manager context exited.")


if __name__ == '__main__':
    main()

