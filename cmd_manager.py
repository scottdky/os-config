#!/usr/bin/env python3
"""Multi-location OS management for localhost, remote SSH, and ARM images/SD cards.

Additional info (multi-line): provides a unified interface for executing commands
and performing basic file operations across three execution contexts:

1. LocalHost - execute commands locally.
2. Remote Host - execute via SSH (requires ``paramiko``).
3. ARM Image/SD Card - execute via chroot with QEMU emulation (requires
   ``qemu-user-static``). Supports both image files (``.img``) and block devices
   (SD cards) and can auto-mount them.

Usage:
    # Remote SSH
    with create_manager('ssh', hostname='192.168.1.100', username='pi') as mgr:
        mgr.run('ls -la', sudo=True)

    # Localhost
    with create_manager('local') as mgr:
        mgr.run('uname -a')

    # Chroot with auto-mount (image file)
    with create_manager('chroot', auto_mount=True,
                       imagePath='/path/to/raspi.img') as mgr:
        mgr.run('apt-get update', sudo=True)

    # Chroot with auto-mount (SD card)
    with create_manager('chroot', auto_mount=True,
                       imagePath='/dev/sdb') as mgr:
        mgr.run('uname -a')

    # Chroot (manual mount - legacy)
    with create_manager('chroot', mount_path='/mnt/image') as mgr:
        mgr.run('apt-get update', sudo=True)
"""
import os
import stat
import shutil
import subprocess
import tempfile
import paramiko
from types import TracebackType


class BaseManager:
    """Base class defining the common interface for all managers"""

    def run(self, command: str, sudo: bool = False) -> tuple[str, str, int]:
        """Execute a command.

        Additional info (multi-line): concrete subclasses implement this to
        run commands in their respective execution contexts and return the
        standard output, standard error, and exit status.

        Args:
            command (str): Command to execute.
            sudo (bool): Whether to run with elevated privileges, if
                supported by the concrete manager.

        Returns:
            tuple[str, str, int]: A tuple of (stdout, stderr, exit_status).
        """
        raise NotImplementedError

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Upload or copy a file to the target.

        Additional info (multi-line): concrete subclasses provide the
        implementation for copying data from the host to the target
        environment (local filesystem, SSH target, or chroot filesystem).

        Args:
            localPath (str): Path to the source file on the host
                filesystem.
            remotePath (str): Destination path as it should appear on the
                target.
            sudo (bool): Whether to use elevated privileges when writing
                the file on the target, if supported.
        """
        raise NotImplementedError

    def exists(self, remotePath: str) -> bool:
        """Check if file/directory exists"""
        raise NotImplementedError

    @staticmethod
    def _normalize_content(content: str | list[str]) -> str:
        """Convert content to string if it's a list"""
        if isinstance(content, list):
            return '\n'.join(content)
        return content

    def _read_file_content(self, remotePath: str, sudo: bool = False) -> str:
        """Read file content using run command. Returns content or empty string."""
        cmd = f'cat {remotePath}'
        output, _, status = self.run(cmd, sudo=sudo)
        return output if status == 0 else ''

    def _run_local(self, command: str) -> tuple[str, str, int]:
        """Run a shell command on the host system.

        Additional info (multi-line): this always executes on the Python
        host rather than inside any remote or chrooted context and returns
        a tuple of standard output, standard error, and exit status.

        Args:
            command (str): The shell command to execute.

        Returns:
            tuple[str, str, int]: A tuple of (stdout, stderr, exit_status).
        """
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            return result.stdout, result.stderr, result.returncode
        except Exception as e:
            return '', str(e), 1

    def _put_local(self, localPath: str, remotePath: str, sudo: bool = False,
                   base_dir: str | None = None, ensure_dir_when_not_sudo: bool = False,
                   label: str | None = None) -> None:
        """Helper for local-style copy (localhost or chroot filesystem).

        Args:
            localPath (str): Source file on the host filesystem.
            remotePath (str): Destination path as seen by the caller.
            sudo (bool): If True, use sudo cp; otherwise regular copy.
            base_dir (str | None): If provided, remotePath is resolved
                relative to this directory.
            ensure_dir_when_not_sudo (bool): If True, create the parent
                directory when not using sudo.
            label (str | None): Optional label to include in log output,
                for example "chroot".
        """

        # Resolve destination path
        if base_dir:
            relPath = remotePath[1:] if remotePath.startswith('/') else remotePath
            destPath = os.path.join(base_dir, relPath)
        else:
            destPath = remotePath

        try:
            if sudo:
                # Use sudo cp command on host
                _, stderr, code = self._run_local(f'sudo cp {localPath} {destPath}')
                if code != 0:
                    context = f" {label}" if label else ''
                    print(f"Error copying file{context}: {stderr}")
                    return
            else:
                if ensure_dir_when_not_sudo:
                    destDir = os.path.dirname(destPath)
                    if destDir:
                        os.makedirs(destDir, exist_ok=True)
                shutil.copy2(localPath, destPath)

            suffix = f" ({label})" if label else ''
            print(f"Copied {localPath} -> {remotePath}{suffix}")
        except Exception as e:
            context = f" {label}" if label else ''
            print(f"Error copying file{context}: {e}")

    def append(self, remotePath: str, content: str | list[str], sudo: bool = False) -> None:
        """Append content to a file (base implementation using shell commands)"""
        content = self._normalize_content(content)

        # Read existing content
        existing = ''
        if self.exists(remotePath):
            existing = self._read_file_content(remotePath, sudo=sudo)

        # Check if content already exists
        if content not in existing:
            # Escape single quotes in content for shell
            escaped_content = content.replace("'", "'\"'\"'")
            new_content = f'\n{escaped_content}\n'

            # Append using shell command
            if sudo:
                self.run(f"echo '{new_content}' | sudo tee -a {remotePath} > /dev/null", sudo=False)
            else:
                self.run(f"echo '{new_content}' >> {remotePath}", sudo=False)
            print(f"Appended to {remotePath}")
        else:
            print(f"Content already exists in {remotePath}")

    def close(self) -> None:
        """Clean up resources"""
        pass

    def __enter__(self) -> "BaseManager":
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self.close()


class LocalManager(BaseManager):
    """Execute operations on localhost"""

    def __init__(self) -> None:
        pass

    def run(self, command: str, sudo: bool = False) -> tuple[str, str, int]:
        """Execute a command on localhost"""
        if sudo:
            command = f'sudo {command}'

        stdout, stderr, code = self._run_local(command)
        if code != 0:
            print(f"Error: {stderr}")
        return stdout, stderr, code

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Copy file locally"""
        self._put_local(localPath, remotePath, sudo=sudo)

    def exists(self, remotePath: str) -> bool:
        """Check if local file/directory exists"""
        return os.path.exists(remotePath)


class SSHManager(BaseManager):
    """Execute operations on remote host via SSH"""

    def __init__(self, hostName: str, userName: str | None = None,
                 keyFilename: str | None = None, password: str | None = None) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {'hostname': hostName}
        if userName:
            connect_kwargs['username'] = userName
        if keyFilename:
            connect_kwargs['key_filename'] = keyFilename
        if password:
            connect_kwargs['password'] = password

        self.client.connect(**connect_kwargs)
        self.sftp = self.client.open_sftp()

    def run(self, command: str, sudo: bool = False) -> tuple[str, str, int]:
        """Execute a command on remote host"""
        if sudo:
            command = f'sudo -S {command}'

        stdin, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()

        output = stdout.read().decode()
        error = stderr.read().decode()

        if exit_status != 0:
            print(f"Error: {error}")
        return output, error, exit_status

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Upload file to remote host"""
        if sudo:
            # Upload to temp location first, then sudo mv
            tempPath = f'/tmp/{os.path.basename(remotePath)}'
            self.sftp.put(localPath, tempPath)
            self.run(f'mv {tempPath} {remotePath}', sudo=True)
        else:
            self.sftp.put(localPath, remotePath)
        print(f"Uploaded {localPath} -> {remotePath}")

    def exists(self, remotePath: str) -> bool:
        """Check if remote file/directory exists"""
        try:
            self.sftp.stat(remotePath)
            return True
        except FileNotFoundError:
            return False

    def close(self) -> None:
        """Close SSH connection"""
        self.sftp.close()
        self.client.close()


class ImageManager(BaseManager):
    """
    Execute operations on a mounted ARM image via chroot with QEMU emulation.

    Prerequisites:
    - qemu-user-static must be installed on the host system
    - If auto_mount=False: The ARM image filesystem must already be mounted at mount_path
    - If auto_mount=True: imagePath must point to an image file or block device (SD card)

    This manager uses chroot with QEMU ARM static emulation to execute commands
    on ARM-based OS images (e.g., Raspberry Pi images) from x86/x64 hosts.
    """

    def __init__(self, mountPath: str = '/mnt/image', autoMount: bool = False,
                 imagePath: str | None = None, keepMounted: bool = False,
                 forceUnmount: bool = False) -> None:
        """
        Initialize ImageManager.

        Args:
            mountPath: Path where the ARM filesystem is/will be mounted (default: /mnt/image)
            autoMount: If True, automatically mount imagePath before operations (default: False)
            imagePath: Path to image file or block device (required if auto_mount=True)
            keepMounted: If True, don't unmount on cleanup (useful for development) (default: False)
            forceUnmount: If True, force-kill processes using mount before unmounting (default: False)
        """
        self.mountPath = mountPath
        self._autoMounted = False
        self._keepMounted = keepMounted
        self._forceUnmount = forceUnmount
        self._hackApplied = False
        self._scriptDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'os')

        # Validate auto_mount parameters
        if autoMount:
            if not imagePath:
                raise ValueError("imagePath is required when auto_mount=True")
            if not os.path.exists(imagePath):
                raise ValueError(f"imagePath does not exist: {imagePath}")

            # Check if already mounted
            if self._is_mounted():
                print(f"{mountPath} is already mounted, skipping auto-mount")
                self._autoMounted = False
            else:
                # Detect and mount
                target_type = self._detect_target_type(imagePath)
                if target_type == 'block_device':
                    print(f"Detected block device: {imagePath}")
                    self._mount_drive(imagePath)
                elif target_type == 'image_file':
                    print(f"Detected image file: {imagePath}")
                    self._mount_image(imagePath)
                else:
                    raise ValueError(f"Unable to determine type of: {imagePath}")
                self._autoMounted = True
        else:
            # Verify mount path exists if not auto-mounting
            if not os.path.exists(mountPath):
                print(f"Warning: Mount path {mountPath} does not exist")

        # Check if qemu-arm-static is available
        _, _, code = self._run_local('which qemu-arm-static')
        if code != 0:
            print("Warning: qemu-arm-static not found. Install with: apt-get install qemu-user-static")

        # Copy qemu-arm-static into the chroot environment
        self._setup_qemu()

    def _is_mounted(self) -> bool:
        """Check if anything is mounted at mount_path"""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    fields = line.split()
                    if len(fields) >= 2 and self.mountPath in fields[1]:
                        return True
            return False
        except Exception as e:
            print(f"Warning: Could not check mount status: {e}")
            # Fallback: check if directory exists
            return os.path.exists(self.mountPath) and os.path.ismount(self.mountPath)

    def _detect_target_type(self, path: str) -> str:
        """Detect if path is a block device or image file"""
        try:
            mode = os.stat(path).st_mode
            if stat.S_ISBLK(mode):
                return 'block_device'
            elif stat.S_ISREG(mode):
                return 'image_file'
            else:
                return 'unknown'
        except (OSError, FileNotFoundError) as e:
            print(f"Error detecting target type: {e}")
            return 'unknown'

    def _mount_image(self, imagePath: str) -> None:
        """Mount an image file using bash script"""
        # Create mount directory
        os.makedirs(self.mountPath, exist_ok=True)

        # Call mnt_image.sh script
        script_path = os.path.join(self._scriptDir, 'mnt_image.sh')
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Mount script not found: {script_path}")

        stdout, stderr, code = self._run_local(
            f'sudo bash {script_path} {imagePath} {self.mountPath}'
        )

        if code != 0:
            raise RuntimeError(f"Failed to mount image: {stderr}")

        print(f"Mounted image: {imagePath} -> {self.mountPath}")

        # Apply ld.so.preload hack for apt-get support
        self._apply_ldpreload_hack()

    def _mount_drive(self, device_path: str) -> None:
        """Mount a block device (SD card) directly"""
        # Create mount directory
        os.makedirs(self.mountPath, exist_ok=True)

        # Mount root partition (partition 2) and boot partition (partition 1)
        rootPartition = f"{device_path}2"
        bootPartition = f"{device_path}1"

        # Mount root
        stdout, stderr, code = self._run_local(
            f'sudo mount {rootPartition} {self.mountPath}'
        )
        if code != 0:
            raise RuntimeError(f"Failed to mount root partition: {stderr}")

        # Mount boot
        bootMountPath = os.path.join(self.mountPath, 'boot')
        os.makedirs(bootMountPath, exist_ok=True)
        stdout, stderr, code = self._run_local(
            f'sudo mount {bootPartition} {bootMountPath}'
        )
        if code != 0:
            print(f"Warning: Failed to mount boot partition: {stderr}")

        print(f"Mounted drive: {device_path} -> {self.mountPath}")

        # Apply ld.so.preload hack for apt-get support
        self._apply_ldpreload_hack()

    def _apply_ldpreload_hack(self) -> None:
        """Apply ld.so.preload hack to enable apt-get in chroot"""
        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"

            if os.path.exists(preloadPath) and not os.path.exists(backupPath):
                _, stderr, code = self._run_local(
                    f'sudo mv {preloadPath} {backupPath}'
                )
                if code == 0:
                    self._hackApplied = True
                    print("Applied ld.so.preload hack for chroot")
                else:
                    print(f"Warning: Could not apply ld.so.preload hack: {stderr}")
        except Exception as e:
            print(f"Warning: Exception applying ld.so.preload hack: {e}")

    def _undo_ldpreload_hack(self) -> None:
        """Restore ld.so.preload before unmounting"""
        if not self._hackApplied:
            return

        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"

            if os.path.exists(backupPath):
                _, stderr, code = self._run_local(
                    f'sudo mv {backupPath} {preloadPath}'
                )
                if code == 0:
                    self._hackApplied = False
                    print("Restored ld.so.preload")
                else:
                    print(f"Warning: Could not restore ld.so.preload: {stderr}")
        except Exception as e:
            print(f"Warning: Exception restoring ld.so.preload: {e}")

    def _setup_qemu(self) -> None:
        """Copy qemu-arm-static into the mounted filesystem"""
        try:
            stdout, _, _ = self._run_local('which qemu-arm-static')
            qemuPath = stdout.strip()

            if qemuPath:
                destPath = os.path.join(self.mountPath, 'usr/bin/qemu-arm-static')
                os.makedirs(os.path.dirname(destPath), exist_ok=True)

                # Use rsync if available, otherwise cp
                _, _, code = self._run_local(f'rsync -aq {qemuPath} {destPath}')
                if code != 0:
                    self._run_local(f'cp {qemuPath} {destPath}')
        except Exception as e:
            print(f"Warning: Could not setup QEMU: {e}")

    def run(self, command: str, sudo: bool = False) -> tuple[str, str, int]:
        """Execute a command in the chroot environment"""
        # Create a temporary script with the command
        script_content = command
        if sudo:
            script_content = f'sudo {command}'

        # Write script to chroot filesystem
        scriptPath = os.path.join(self.mountPath, 'chroot_script.sh')
        try:
            with open(scriptPath, 'w') as f:
                f.write(f'#!/bin/bash\n{script_content}\n')
            os.chmod(scriptPath, 0o755)

            # Execute via chroot
            chrootCmd = f'chroot {self.mountPath} /usr/bin/qemu-arm-static /bin/bash /chroot_script.sh'
            stdout, stderr, code = self._run_local(chrootCmd)

            # Cleanup
            if os.path.exists(scriptPath):
                os.remove(scriptPath)

            if code != 0:
                print(f"Error: {stderr}")

            return stdout, stderr, code
        except Exception as e:
            error_msg = str(e)
            print(f"Error executing chroot command: {error_msg}")
            # Cleanup on error
            if os.path.exists(scriptPath):
                os.remove(scriptPath)
            return '', error_msg, 1

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Copy file into the chroot filesystem"""
        # Use shared local-style copy helper with chroot-specific base_dir
        self._put_local(localPath=localPath, remotePath=remotePath, sudo=sudo,
                        base_dir=self.mountPath, ensure_dir_when_not_sudo=True,
                        label='chroot')

    def exists(self, remotePath: str) -> bool:
        """Check if file/directory exists in chroot filesystem"""
        if remotePath.startswith('/'):
            remotePath = remotePath[1:]

        destPath = os.path.join(self.mountPath, remotePath)
        return os.path.exists(destPath)

    def close(self) -> None:
        """Clean up and unmount if auto-mounted"""
        if self._autoMounted and not self._keepMounted:
            self._unmount()

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> bool:
        """Ensure cleanup happens even on exceptions"""
        try:
            # Always attempt cleanup, even if there was an exception
            self.close()
        except Exception as cleanup_error:
            print(f"Warning: Error during cleanup: {cleanup_error}")
            # Don't suppress the original exception
        return False

    def _unmount(self) -> None:
        """Unmount the filesystem"""
        try:
            # Restore ld.so.preload hack first
            self._undo_ldpreload_hack()

            # Use unmount script for proper nested unmount handling
            scriptPath = os.path.join(self._scriptDir, 'unmnt_image.sh')
            if not os.path.exists(scriptPath):
                print(f"Warning: Unmount script not found: {scriptPath}")
                # Fallback: simple unmount
                self._run_local(f'sudo umount -R {self.mountPath}')
            else:
                forceFlag = 'force' if self._forceUnmount else ''
                _, stderr, code = self._run_local(
                    f'sudo bash {scriptPath} {self.mountPath} {forceFlag}'
                )
                if code != 0:
                    print(f"Warning: Unmount script errors: {stderr}")

            # Remove mount directory
            if os.path.exists(self.mountPath):
                try:
                    os.rmdir(self.mountPath)
                except OSError:
                    # Directory not empty or other issue
                    pass

            print(f"Unmounted: {self.mountPath}")
            self._autoMounted = False
        except Exception as e:
            print(f"Error during unmount: {e}")
            raise


def create_manager(mode: str, **kwargs) -> BaseManager:
    """Factory function to create the appropriate manager for a mode.

    Additional info (multi-line): this convenience function selects the
    correct manager implementation based on the ``mode`` argument and
    forwards any additional keyword arguments to the constructor.

    Args:
        mode (str): One of ``"local"``, ``"ssh"``, or ``"chroot"``.
        **kwargs: Additional arguments passed through to the manager
            constructor for the selected mode.

    Returns:
        BaseManager: An instance of ``LocalManager``, ``SSHManager``, or
        ``ImageManager`` depending on the requested mode.

    Examples:
        # Local execution
        mgr = create_manager('local')

        # Remote SSH
        mgr = create_manager('ssh', hostname='192.168.1.100', username='pi',
                           key_filename='/home/user/.ssh/id_rsa')

        # Chroot - manual mount (legacy)
        mgr = create_manager('chroot', mount_path='/mnt/image')

        # Chroot - auto-mount image file
        mgr = create_manager('chroot', auto_mount=True,
                           imagePath='/path/to/raspi.img')

        # Chroot - auto-mount SD card
        mgr = create_manager('chroot', auto_mount=True,
                           imagePath='/dev/sdb')

        # Chroot - keep mounted for development
        mgr = create_manager('chroot', auto_mount=True,
                           imagePath='/path/to/raspi.img',
                           keep_mounted=True)
    """
    mode = mode.lower()

    if mode == 'local':
        return LocalManager()
    elif mode == 'ssh':
        return SSHManager(**kwargs)
    elif mode == 'chroot':
        return ImageManager(**kwargs)
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'local', 'ssh', or 'chroot'")


