#!/usr/bin/env python3
"""Multi-location OS management for localhost, remote SSH, and ARM images/SD cards.

Additional info (multi-line): provides a unified interface for executing commands
and performing basic file operations across three execution contexts:

1. LocalHost - execute commands locally.
2. Remote Host - execute via SSH (requires ``paramiko``).
3. ARM Image/SD Card - execute via chroot with QEMU emulation (requires
   ``qemu-user-static``). Supports both image files (``.img``) and block devices
   (SD cards) with automatic mount detection and smart reuse of existing mounts.

Usage:
    # Remote SSH
    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        mgr.run('ls -la', sudo=True)

    # Localhost
    with create_manager('local') as mgr:
        mgr.run('uname -a')

    # Image file (auto-detects existing loop mounts)
    with create_manager('image', imagePath='/path/to/raspi.img') as mgr:
        mgr.run('apt-get update', sudo=True)

    # SD card with known device path
    with create_manager('sdcard', devicePath='/dev/sdb') as mgr:
        mgr.run('hostname')

    # SD card with interactive USB device selection
    with create_manager('sdcard', interactive=True) as mgr:
        mgr.run('apt-get update', sudo=True)
"""
import os
import sys
import stat
import shutil
import subprocess
import tempfile
import re
import shlex
import paramiko
from dataclasses import dataclass
from types import TracebackType
from typing import cast
from simple_term_menu import TerminalMenu

DEFAULT_MOUNT_PATH = '/tmp/os_image'


@dataclass
class CommandResult:
    """Normalized command execution result.

    Additional info (multi-line): this wraps command output in a stable
    project-local shape while preserving backward compatibility for existing
    tuple-unpacking code paths.
    """
    stdout: str
    stderr: str
    returnCode: int

    def __iter__(self):
        """Allow tuple-style unpacking: stdout, stderr, code = result."""
        yield self.stdout
        yield self.stderr
        yield self.returnCode

def get_user_selection(options: list[str], title: str = 'Select operation', addExit: str | bool = 'Exit') -> int | None:
    """Prompt user to select the operation when not provided on the CLI.

    Args:
        options (list[str]): List of options to display.
        title (str): Title for the selection menu.
        addExit (str | bool): Exit option label. Pass a string to customize the label,
            False to disable, or 'Exit' (default) for standard exit behavior.

    Returns:
        int | None: Index of the selected operation, or None if cancelled.
    """
    menuOptions = options.copy()
    if addExit is True:
        addExit = 'Exit'
    if addExit:
        menuOptions.append(addExit)

    menu = TerminalMenu(menuOptions, title=title)
    menuEntryIndex = cast(int | None, menu.show()) # hack to avoid error about possible tuple return type from show()
    if menuEntryIndex is None:
        return None
    if addExit and menuEntryIndex == len(menuOptions) - 1:
        return None # Exit was chosen

    return menuEntryIndex


class BaseManager:
    """Base class defining the common interface for all managers"""

    def __init__(self, allowInteractiveSudo: bool = True) -> None:
        """Initialize shared manager state.

        Args:
            allowInteractiveSudo (bool): Default policy for whether local sudo
                validation may prompt interactively via ``sudo -v``.
        """
        self.allowInteractiveSudo = allowInteractiveSudo

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command.

        Additional info (multi-line): concrete subclasses implement this to
        run commands in their respective execution contexts and return the
        standard output, standard error, and exit status.

        Args:
            command (str): Command to execute.
            sudo (bool): Whether to run with elevated privileges, if
                supported by the concrete manager.

        Returns:
            CommandResult: Standardized command output and exit status.
        """
        raise NotImplementedError

    def exists(self, remotePath: str) -> bool:
        """Check if file/directory exists"""
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

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Download a file from the target to local filesystem.

        Args:
            remotePath (str): Source path on target.
            localPath (str): Destination path on local filesystem.
            sudo (bool): Whether to use elevated privileges for reading.
        """
        raise NotImplementedError

    def read_file(self, remotePath: str, sudo: bool = False) -> str:
        """Read file content and return as string.

        Args:
            remotePath (str): Path to file on target.
            sudo (bool): Whether to use elevated privileges.

        Returns:
            str: File content or empty string on error.
        """
        cmd = f'cat {remotePath}'
        output, _, status = self.run(cmd, sudo=sudo)
        return output if status == 0 else ''

    def write_file(self, remotePath: str, content: str, sudo: bool = False) -> None:
        """Replace entire contents of a file.

        Args:
            remotePath (str): Path to the target file.
            content (str): New content to write.
            sudo (bool): Whether to use elevated privileges.
        """
        fd, tempPath = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            self.put(tempPath, remotePath, sudo=sudo)
        finally:
            if os.path.exists(tempPath):
                os.remove(tempPath)

    def append(self, remotePath: str, content: str | list[str], sudo: bool = False) -> None:
        """
        Append content to a remote file (only if not existing),
        or uncomment if present but commented out.

        Args:
            remotePath (str): Path to the target file on the remote system.
            content (str | list[str]): Content to append or uncomment.
            sudo (bool, optional): Whether to use elevated privileges. Defaults to False.
        """
        if isinstance(content, str):
            lines_to_add = [l for l in content.splitlines() if l.strip()]
        else:
            lines_to_add = [l for l in content if l.strip()]

        if not lines_to_add:
            return

        # Read existing content
        existing_content = ''
        if self.exists(remotePath):
            existing_content = self.read_file(remotePath, sudo=sudo)

        # Split existing content into lines
        existing_lines = existing_content.splitlines()

        modified = False

        for line in lines_to_add:
            # Check 1: Exact match
            if line in existing_lines:
                continue

            # Check 2: Commented match
            escape_line = re.escape(line)
            # Regex: start of line, optional whitespace, #, optional whitespace, exact line content, trailing whitespace, end of line
            pattern = re.compile(r'^\s*#\s*' + escape_line + r'\s*$')

            found_commented = False
            for i, existing_line in enumerate(existing_lines):
                if pattern.match(existing_line):
                    existing_lines[i] = line
                    modified = True
                    found_commented = True
                    print(f"Uncommented line in {remotePath}: {line.strip()[:50]}...")
                    break

            if found_commented:
                continue

            # Check 3: Append
            existing_lines.append(line)
            modified = True
            print(f"Appended to {remotePath}: {line.strip()[:50]}...")

        if modified:
            new_content = '\n'.join(existing_lines) + '\n'

            fd, temp_path = tempfile.mkstemp()
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(new_content)
                self.put(temp_path, remotePath, sudo=sudo)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            print(f"No changes made to {remotePath}")

    def sed(self, remotePath: str, before: str, after: str, useRegex: bool = False,
            limit: int = 0, backup: str = '.bak', sudo: bool = False) -> None:
        """
        Perform in-place search and replace on a file (like sed -i).

        Additional info (multi-line): replaces occurrences of a pattern in a file
        with new text. Supports both literal string replacement and regex patterns.
        Optionally creates a backup before modifying. Can limit the number of
        replacements or replace all matches.

        Args:
            remotePath (str): Path to the target file.
            before (str): Pattern to search for (regex if useRegex=True, else literal).
            after (str): Replacement text (can include backreferences like \\1, \\2 if useRegex=True).
            limit (int): Maximum number of replacements (0 = replace all).
            useRegex (bool): If True, treat 'before' as regex; if False, literal string.
            backup (str): Backup extension (e.g., '.bak'). Set to empty string '' to skip backup.
            sudo (bool): Whether to use elevated privileges.
        """
        if not self.exists(remotePath):
            print(f"File not found: {remotePath}")
            return

        # Read existing content
        existing_content = self.read_file(remotePath, sudo=sudo)
        if not existing_content:
            print(f"Could not read file: {remotePath}")
            return

        # Perform replacement
        if useRegex:
            if limit == 0:
                newContent = re.sub(before, after, existing_content)
            else:
                newContent = re.sub(before, after, existing_content, count=limit)
        else:
            # Literal string replacement
            if limit == 0:
                newContent = existing_content.replace(before, after)
            else:
                newContent = existing_content.replace(before, after, limit)

        # Check if anything changed
        if newContent == existing_content:
            print(f"No changes made to {remotePath} (pattern not found)")
            return

        # Create backup if requested
        if backup:
            backupPath = f"{remotePath}{backup}"
            fd, tempBackup = tempfile.mkstemp()
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(existing_content)
                self.put(tempBackup, backupPath, sudo=sudo)
                print(f"Created backup: {backupPath}")
            finally:
                if os.path.exists(tempBackup):
                    os.remove(tempBackup)

        # Write modified content
        fd, tempPath = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(newContent)
            self.put(tempPath, remotePath, sudo=sudo)
            print(f"Modified {remotePath}")
        finally:
            if os.path.exists(tempPath):
                os.remove(tempPath)

    def _run_local(self, command: str, sudo: bool = False,
                   allowInteractiveSudo: bool | None = None) -> CommandResult:
        """Run a shell command on the host system.

          Additional info (multi-line): this always executes on the Python
          host rather than inside any remote or chrooted context.

          Safe sudo flow for multi-step processes:
          1) Try non-interactive sudo (``sudo -n``) to avoid hanging prompts.
          2) If sudo timestamp is expired and interactive fallback is allowed,
              prompt once via ``sudo -v``.
          3) Retry the command non-interactively.

        Args:
            command (str): The shell command to execute.
            sudo (bool): Whether to run command with elevated privileges.
            allowInteractiveSudo (bool | None): Whether to attempt a one-time
                interactive sudo refresh when non-interactive sudo fails. If
                ``None``, use manager-level default policy.

        Returns:
            CommandResult: Standardized command output and exit status.
        """
        def _exec(commandArgs: list[str]) -> CommandResult:
            result = subprocess.run(commandArgs, capture_output=True, text=True, check=False)
            return CommandResult(result.stdout, result.stderr, result.returncode)

        effectiveAllowInteractiveSudo = self.allowInteractiveSudo if allowInteractiveSudo is None else allowInteractiveSudo

        try:
            if not sudo:
                return _exec(['bash', '-lc', command])

            sudoCheckResult = self.validate_sudo(allowInteractiveSudo=effectiveAllowInteractiveSudo)
            if sudoCheckResult.returnCode != 0:
                return sudoCheckResult

            return _exec(['sudo', '-n', 'bash', '-lc', command])
        except Exception as e:
            return CommandResult('', str(e), 1)

    def validate_sudo(self, allowInteractiveSudo: bool | None = None) -> CommandResult:
        """Validate local sudo availability for privileged host commands.

        Additional info (multi-line): first checks non-interactive sudo to avoid
        hanging prompts. If authentication is required and interactive fallback
        is enabled, it runs ``sudo -v`` once, then verifies non-interactive sudo
        again.

        Args:
            allowInteractiveSudo (bool | None): Whether to allow a one-time
                interactive sudo refresh when non-interactive validation fails.
                If ``None``, use manager-level default policy.

        Returns:
            CommandResult: Validation outcome where returnCode 0 means sudo is
            ready for non-interactive command execution.
        """
        def _exec(commandArgs: list[str]) -> CommandResult:
            result = subprocess.run(commandArgs, capture_output=True, text=True, check=False)
            return CommandResult(result.stdout, result.stderr, result.returncode)

        def _requires_auth(stderr: str) -> bool:
            lowerStderr = stderr.lower()
            return (
                'a password is required' in lowerStderr or
                'no tty present and no askpass program specified' in lowerStderr or
                'sudo: authentication is required' in lowerStderr
            )

        effectiveAllowInteractiveSudo = self.allowInteractiveSudo if allowInteractiveSudo is None else allowInteractiveSudo

        try:
            sudoCheckResult = _exec(['sudo', '-n', 'true'])
            if sudoCheckResult.returnCode == 0:
                return sudoCheckResult

            if not _requires_auth(sudoCheckResult.stderr) or not effectiveAllowInteractiveSudo:
                return sudoCheckResult

            refreshResult = _exec(['sudo', '-v'])
            if refreshResult.returnCode != 0:
                stderr = refreshResult.stderr.strip() or 'sudo authentication failed (sudo -v)'
                return CommandResult(refreshResult.stdout, stderr, refreshResult.returnCode)

            return _exec(['sudo', '-n', 'true'])
        except Exception as e:
            return CommandResult('', str(e), 1)

    def _ensure_local_directory(self, path: str, sudo: bool = False) -> CommandResult:
        """Ensure a host-side directory exists.

        Additional info (multi-line): when ``sudo=True``, this uses the
        manager's sudo-aware local execution path so protected mount locations
        (for example under ``/mnt``) can be created reliably.

        Args:
            path (str): Directory path to create.
            sudo (bool): Whether directory creation should run with elevated
                privileges.

        Returns:
            CommandResult: Operation status where returnCode 0 means the
            directory exists or was created.
        """
        if not path:
            return CommandResult('', 'Directory path is required', 1)

        if sudo:
            return self._run_local(f'mkdir -p {shlex.quote(path)}', sudo=True)

        try:
            os.makedirs(path, exist_ok=True)
            return CommandResult('', '', 0)
        except Exception as e:
            return CommandResult('', str(e), 1)

    def _remove_local_directory(self, path: str, sudo: bool = False) -> CommandResult:
        """Remove a host-side directory if it exists and is empty.

        Args:
            path (str): Directory path to remove.
            sudo (bool): Whether removal should run with elevated privileges.

        Returns:
            CommandResult: Operation result. Missing directories are treated as
            success.
        """
        if not path or not os.path.exists(path):
            return CommandResult('', '', 0)

        if sudo:
            return self._run_local(f'rmdir {shlex.quote(path)}', sudo=True)

        try:
            os.rmdir(path)
            return CommandResult('', '', 0)
        except Exception as e:
            return CommandResult('', str(e), 1)

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
                directory before copying. When sudo is used, directory
                creation also runs with sudo.
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
            if ensure_dir_when_not_sudo:
                destDir = os.path.dirname(destPath)
                if destDir:
                    mkdirResult = self._ensure_local_directory(destDir, sudo=sudo)
                    if mkdirResult.returnCode != 0:
                        context = f" {label}" if label else ''
                        print(f"Error creating destination directory{context}: {mkdirResult.stderr}")
                        return

            if sudo:
                # Use sudo cp command on host
                _, stderr, code = self._run_local(
                    f'cp {shlex.quote(localPath)} {shlex.quote(destPath)}',
                    sudo=True
                )
                if code != 0:
                    context = f" {label}" if label else ''
                    print(f"Error copying file{context}: {stderr}")
                    return
            else:
                shutil.copy2(localPath, destPath)

            suffix = f" ({label})" if label else ''
            print(f"Copied {localPath} -> {remotePath}{suffix}")
        except Exception as e:
            context = f" {label}" if label else ''
            print(f"Error copying file{context}: {e}")

    def close(self) -> None:
        """Clean up resources"""
        pass

    def __enter__(self) -> "BaseManager":
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self.close()


class LocalManager(BaseManager):
    """Execute operations on localhost"""

    def __init__(self, allowInteractiveSudo: bool = True) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command on localhost"""
        stdout, stderr, code = self._run_local(command, sudo=sudo)
        if code != 0:
            print(f"Error: {stderr}")
        return CommandResult(stdout, stderr, code)

    def exists(self, remotePath: str) -> bool:
        """Check if local file/directory exists"""
        return os.path.exists(remotePath)

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Copy file locally"""
        self._put_local(localPath, remotePath, sudo=sudo)

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Copy file from local system to another local path"""
        if sudo:
            _, stderr, code = self._run_local(
                f'cp {shlex.quote(remotePath)} {shlex.quote(localPath)}',
                sudo=True
            )
            if code != 0:
                raise IOError(f"Failed to copy {remotePath} to {localPath}: {stderr}")
        else:
            shutil.copy(remotePath, localPath)
        print(f"Downloaded {remotePath} -> {localPath}")


class SSHManager(BaseManager):
    """Execute operations on remote host via SSH"""

    def __init__(self, hostName: str, userName: str | None = None,
                 keyFilename: str | None = None, password: str | None = None,
                 allowInteractiveSudo: bool = True) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)
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

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command on remote host"""
        if sudo:
            command = f'sudo -S {command}'

        stdin, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()

        output = stdout.read().decode()
        error = stderr.read().decode()

        if exit_status != 0:
            print(f"Error: {error}")
        return CommandResult(output, error, exit_status)

    def exists(self, remotePath: str) -> bool:
        """Check if remote file/directory exists"""
        try:
            self.sftp.stat(remotePath)
            return True
        except FileNotFoundError:
            return False

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

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Download file from remote host"""
        if sudo:
            # Copy to temp location with sudo, then download
            tempPath = f'/tmp/{os.path.basename(remotePath)}'
            self.run(f'cp {remotePath} {tempPath}', sudo=True)
            self.run(f'chmod 644 {tempPath}', sudo=True)
            self.sftp.get(tempPath, localPath)
            self.run(f'rm {tempPath}', sudo=False)
        else:
            self.sftp.get(remotePath, localPath)
        print(f"Downloaded {remotePath} -> {localPath}")

    def close(self) -> None:
        """Close SSH connection"""
        self.sftp.close()
        self.client.close()


class BaseImageManager(BaseManager):
    """
    Abstract base class for ARM image management via chroot with QEMU emulation.

    Provides common functionality for both image files and SD cards including:
    - chroot execution with QEMU ARM static emulation
    - ld.so.preload hack management for apt-get support
    - QEMU setup
    - File operations (put/get/exists)
    - Mount state tracking
    - Cleanup and unmount logic

    Subclasses must implement:
    - _perform_mount(): Mount the target
    - _validate_target(): Validate target exists and is correct type
    """

    def __init__(self, mountPath: str = DEFAULT_MOUNT_PATH, forceUnmount: bool = False,
                 allowInteractiveSudo: bool = True, defaultChrootUser: str | None = None,
                 keepMounted: bool = False) -> None:
        """
        Initialize BaseImageManager.

        Args:
            mountPath: Path where the ARM filesystem is/will be mounted (default: DEFAULT_MOUNT_PATH)
            forceUnmount: If True, force-kill processes using mount before unmounting (default: False)
            allowInteractiveSudo: Whether local sudo validation can prompt interactively.
            defaultChrootUser: Non-root user (``user`` or ``uid:gid``) used for
                chroot commands when ``sudo=False``. If None, run as root.
            keepMounted: If True, skip automatic unmount during manager close.
        """
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)
        self.mountPath = mountPath
        self._mountedByUs = {}  # Track what we mounted: {'root': True, 'boot': True, ...}
        self._forceUnmount = forceUnmount
        self.keepMounted = keepMounted
        self._hackApplied = False
        self._qemuStaticBinary = 'qemu-arm-static'
        self.defaultChrootUser = defaultChrootUser
        # Script directory is at project root /os, not /lib/os
        libDir = os.path.dirname(os.path.abspath(__file__))
        projectRoot = os.path.dirname(libDir)
        self._scriptDir = os.path.join(projectRoot, 'os')

        sudoCheckResult = self.validate_sudo()
        if sudoCheckResult.returnCode != 0:
            raise RuntimeError(f"Sudo validation failed: {sudoCheckResult.stderr}")

        # Validate target and perform mount
        self._validate_target()
        self._perform_mount()

        # Copy appropriate QEMU static binary into the chroot environment
        self._setup_qemu()

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command in the chroot environment.

        Additional info (multi-line): host-side chroot execution requires
        elevated privileges. In-chroot user identity is controlled
        independently: when ``sudo=True``, command runs as root; when
        ``sudo=False``, command runs as ``defaultChrootUser`` if configured,
        otherwise root.
        """
        userspecArg = ''
        if not sudo and self.defaultChrootUser:
            userspecArg = f'--userspec={shlex.quote(self.defaultChrootUser)} '

        chrootCmd = (
            f'chroot {userspecArg}{shlex.quote(self.mountPath)} '
            f'/usr/bin/{self._qemuStaticBinary} /bin/bash -lc {shlex.quote(command)}'
        )
        stdout, stderr, code = self._run_local(chrootCmd, sudo=True)
        if code != 0:
            print(f"Error: {stderr}")
        return CommandResult(stdout, stderr, code)

    def exists(self, remotePath: str) -> bool:
        """Check if file/directory exists in chroot filesystem"""
        if remotePath.startswith('/'):
            remotePath = remotePath[1:]

        destPath = os.path.join(self.mountPath, remotePath)
        return os.path.exists(destPath)

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Copy file into the chroot filesystem"""
        # Use shared local-style copy helper with chroot-specific base_dir
        self._put_local(localPath=localPath, remotePath=remotePath, sudo=sudo,
                        base_dir=self.mountPath, ensure_dir_when_not_sudo=True,
                        label='chroot')

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Copy file from chroot filesystem to local system"""
        # Resolve source path
        relPath = remotePath[1:] if remotePath.startswith('/') else remotePath
        sourcePath = os.path.join(self.mountPath, relPath)

        if not os.path.exists(sourcePath):
            raise FileNotFoundError(f"File not found in chroot: {sourcePath}")

        if sudo:
            _, stderr, code = self._run_local(
                f'cp {shlex.quote(sourcePath)} {shlex.quote(localPath)}',
                sudo=True
            )
            if code != 0:
                raise IOError(f"Failed to copy {sourcePath} to {localPath}: {stderr}")
        else:
            shutil.copy(sourcePath, localPath)
        print(f"Downloaded (chroot) {remotePath} -> {localPath}")

    def _validate_target(self) -> None:
        """Validate target exists and is correct type - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _validate_target()")

    def _perform_mount(self) -> None:
        """Perform the actual mount operation - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _perform_mount()")

    def _perform_unmount(self) -> None:
        """Perform unmount operation via centralized unmount script."""
        self._run_unmount_script(forceUnmount=self._forceUnmount)

    def _run_unmount_script(self, forceUnmount: bool) -> None:
        """Run centralized unmount script with optional force cleanup."""
        scriptPath = os.path.join(self._scriptDir, 'unmnt_image.sh')
        forceFlag = ' force' if forceUnmount else ''
        _, stderr, code = self._run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(self.mountPath)}{forceFlag}'
        )
        if code != 0:
            print(f"Warning: Unmount script errors: {stderr}")

    def _apply_ldpreload_hack(self) -> None:
        """Apply ld.so.preload hack to enable apt-get in chroot"""
        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"

            if os.path.exists(preloadPath) and not os.path.exists(backupPath):
                _, stderr, code = self._run_local(
                    f'mv {shlex.quote(preloadPath)} {shlex.quote(backupPath)}',
                    sudo=True
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
                    f'mv {shlex.quote(backupPath)} {shlex.quote(preloadPath)}',
                    sudo=True
                )
                if code == 0:
                    self._hackApplied = False
                    print("Restored ld.so.preload")
                else:
                    print(f"Warning: Could not restore ld.so.preload: {stderr}")
        except Exception as e:
            print(f"Warning: Exception restoring ld.so.preload: {e}")

    def _setup_qemu(self) -> None:
        """Copy architecture-matching QEMU static binary into mounted filesystem."""
        try:
            self._qemuStaticBinary = self._detect_qemu_static_binary()
            stdout, _, code = self._run_local(f'which {shlex.quote(self._qemuStaticBinary)}')
            if code != 0:
                print(
                    f"Warning: {self._qemuStaticBinary} not found. "
                    "Install with: apt-get install qemu-user-static"
                )
                return

            qemuPath = stdout.strip()

            if qemuPath:
                destPath = os.path.join(self.mountPath, f'usr/bin/{self._qemuStaticBinary}')
                destDirResult = self._ensure_local_directory(os.path.dirname(destPath), sudo=True)
                if destDirResult.returnCode != 0:
                    print(f"Warning: Could not create QEMU destination directory: {destDirResult.stderr}")
                    return

                # Use rsync if available, otherwise cp
                _, _, code = self._run_local(
                    f'rsync -aq {shlex.quote(qemuPath)} {shlex.quote(destPath)}',
                    sudo=True
                )
                if code != 0:
                    self._run_local(f'cp {shlex.quote(qemuPath)} {shlex.quote(destPath)}', sudo=True)
        except Exception as e:
            print(f"Warning: Could not setup QEMU: {e}")

    def _detect_qemu_static_binary(self) -> str:
        """Detect the mounted target architecture and choose matching QEMU binary."""
        targetBashPath = os.path.join(self.mountPath, 'usr/bin/bash')
        stdout, stderr, code = self._run_local(
            f'readelf -h {shlex.quote(targetBashPath)}',
            sudo=True
        )

        if code != 0:
            print(f"Warning: Could not detect target architecture from {targetBashPath}: {stderr}")
            return 'qemu-arm-static'

        for line in stdout.splitlines():
            strippedLine = line.strip()
            if strippedLine.startswith('Machine:'):
                if 'AArch64' in strippedLine:
                    return 'qemu-aarch64-static'
                if 'ARM' in strippedLine:
                    return 'qemu-arm-static'

        print("Warning: Unknown target architecture in ELF header, defaulting to qemu-arm-static")
        return 'qemu-arm-static'

    def close(self) -> None:
        """Clean up and unmount if we mounted it"""
        if self.keepMounted:
            print(f"Keeping mounts active at {self.mountPath} (keepMounted=True)")
            return

        if self._is_mount_active() or any(self._mountedByUs.values()):
            self._unmount()

    def _is_mount_active(self) -> bool:
        """Return True if mountPath currently has an active mount target."""
        _, _, code = self._run_local(f'findmnt -T {shlex.quote(self.mountPath)}', sudo=True)
        return code == 0

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> bool:
        """Ensure cleanup happens even on exceptions"""
        try:
            self.close()
        except Exception as cleanup_error:
            print(f"Warning: Error during cleanup: {cleanup_error}")
        return False

    def _unmount(self) -> None:
        """Unmount the filesystem - only unmounts what we mounted"""
        try:
            # Restore ld.so.preload hack first
            self._undo_ldpreload_hack()

            # Let subclass handle specific unmount logic
            self._perform_unmount()

            print(f"Unmounted: {self.mountPath}")
            self._mountedByUs.clear()
        except Exception as e:
            print(f"Error during unmount: {e}")
            raise


class ImageFileManager(BaseImageManager):
    """
    Execute operations on a mounted ARM image file via chroot with QEMU emulation.

    Handles .img files with automatic detection of existing loop mounts.
    If the image is already loop-mounted, reuses the existing mount.
    Only unmounts what this manager mounted.

    Prerequisites:
    - qemu-user-static must be installed on the host system
    - Image file must exist

    Example:
        with ImageFileManager(imagePath='/path/to/raspi.img') as mgr:
            mgr.run('apt-get update', sudo=True)
    """

    NETWORK_FILESYSTEM_TYPES = {
        'nfs', 'nfs4', 'cifs', 'smb', 'smb2', 'smb3', 'sshfs', 'fuse.sshfs',
        'fuse', 'glusterfs', 'ceph', 'ceph-fuse', '9p', 'afp', 'davfs2'
    }
    STAGE_THRESHOLD_BYTES = int(2.5 * 1024 * 1024 * 1024)
    FIXTURE_PATH_FRAGMENT = os.path.normpath('tests/integration/fixtures')

    def __init__(self, imagePath: str, mountPath: str = DEFAULT_MOUNT_PATH,
                 forceUnmount: bool = False, allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        """
        Initialize ImageFileManager.

        Args:
            imagePath: Path to the .img file
            mountPath: Path where filesystem will be mounted (default: DEFAULT_MOUNT_PATH)
            forceUnmount: If True, force-kill processes before unmounting (default: False)
            allowInteractiveSudo: Whether local sudo validation can prompt interactively.
            defaultChrootUser: Non-root user for chroot commands when ``sudo=False``.
            keepMounted: If True, skip automatic unmount during manager close.
        """
        self.imagePath = imagePath
        self._stagedImagePath = None
        super().__init__(
            mountPath=mountPath,
            forceUnmount=forceUnmount,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
            keepMounted=keepMounted,
        )

    def close(self) -> None:
        """Clean up mounted resources and any staged image copy."""
        try:
            super().close()
        finally:
            self._cleanup_staged_image()

    def _validate_target(self) -> None:
        """Validate image file exists and is a regular file"""
        if not os.path.exists(self.imagePath):
            raise ValueError(f"Image file does not exist: {self.imagePath}")

        mode = os.stat(self.imagePath).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"Not a regular file: {self.imagePath}")

    def _perform_mount(self) -> None:
        """Mount the image file, reusing existing loop mount if available"""
        # Check if image is already loop-mounted
        existingMount = self._find_existing_loop_mount()
        if existingMount:
            print(f"Image already loop-mounted at: {existingMount}")
            print(f"Reusing existing mount (will not unmount on cleanup)")
            self.mountPath = existingMount
            # Don't track as ours since we didn't mount it
            self._mountedByUs = {}
            # Still apply hack if needed
            self._apply_ldpreload_hack()
            return

        imagePathForMount = self._prepare_image_path_for_mount()

        # Not mounted, so mount it ourselves
        scriptPath = os.path.join(self._scriptDir, 'mnt_image.sh')
        stdout, stderr, code = self._run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(imagePathForMount)} {shlex.quote(self.mountPath)}'
        )

        if code != 0:
            self._cleanup_staged_image()
            raise RuntimeError(f"Failed to mount image: {stderr}")

        # Verify root mount is present (guards against partial script success)
        _, verifyErr, verifyCode = self._run_local(f'findmnt -T {self.mountPath}')
        if verifyCode != 0:
            # Attempt cleanup before raising
            self._run_unmount_script(forceUnmount=True)
            self._cleanup_staged_image()
            raise RuntimeError(
                f"Image mount verification failed at {self.mountPath}. "
                f"Script output: {stdout}\n{stderr}\n{verifyErr}"
            )

        print(f"Mounted image: {self.imagePath} -> {self.mountPath}")

        # Track that we mounted this
        self._mountedByUs = {'root': True, 'boot': True}

        # Apply ld.so.preload hack for apt-get support
        self._apply_ldpreload_hack()

    def _perform_unmount(self) -> None:
        """Unmount image mounts and always remove any staged temp image copy."""
        try:
            super()._perform_unmount()
        finally:
            self._cleanup_staged_image()

    def _find_existing_loop_mount(self) -> str | None:
        """Check if image file is already loop-mounted, return mount point if found"""
        try:
            # Get absolute path for comparison
            absImagePath = os.path.abspath(self.imagePath)

            # Find loop device(s) for this image
            stdout, _, code = self._run_local(f'losetup -j {absImagePath}')
            if code != 0 or not stdout.strip():
                return None

            # Parse losetup output: /dev/loop0: []: (/path/to/image.img), offset ...
            # Look for the root partition mount (not boot)
            for line in stdout.splitlines():
                if not line.strip():
                    continue

                # Extract loop device name
                loopDev = line.split(':')[0].strip()

                # Check /proc/mounts for this loop device
                with open('/proc/mounts', 'r') as f:
                    for mountLine in f:
                        fields = mountLine.split()
                        if len(fields) < 2:
                            continue

                        sourceDev = fields[0]
                        # Exact device match only, or explicit partition form (/dev/loopXpN).
                        # Avoid substring collisions like /dev/loop1 matching /dev/loop10.
                        isExactLoop = (sourceDev == loopDev)
                        isLoopPartition = (
                            sourceDev.startswith(f"{loopDev}p") and
                            sourceDev[len(loopDev) + 1:].isdigit()
                        )

                        if isExactLoop or isLoopPartition:
                            mountpoint = fields[1]
                            # Skip boot partition mounts (usually end in /boot)
                            if not mountpoint.endswith('/boot'):
                                return mountpoint

            return None
        except Exception as e:
            print(f"Warning: Error checking for existing loop mount: {e}")
            return None

    def _prepare_image_path_for_mount(self) -> str:
        """Resolve image path for mount, staging network-backed files when needed."""
        absImagePath = os.path.abspath(self.imagePath)
        if not self._is_network_mounted_path(absImagePath):
            return absImagePath

        imageSizeBytes = os.path.getsize(absImagePath)
        shouldAutoStage = (
            self._is_in_integration_fixtures(absImagePath) or
            imageSizeBytes <= self.STAGE_THRESHOLD_BYTES
        )

        if shouldAutoStage:
            return self._stage_image_to_temp(absImagePath, imageSizeBytes)

        memoryAvailableBytes = self._get_available_memory_bytes()
        tmpFreeBytes = self._get_tmp_available_bytes()
        if not self._confirm_stage_large_image(imageSizeBytes, memoryAvailableBytes, tmpFreeBytes):
            raise RuntimeError(
                f"Image is on a network mount and is too large for automatic staging: {absImagePath}. "
                f"Size={self._format_bytes(imageSizeBytes)}, threshold={self._format_bytes(self.STAGE_THRESHOLD_BYTES)}"
            )

        return self._stage_image_to_temp(absImagePath, imageSizeBytes)

    def _is_network_mounted_path(self, path: str) -> bool:
        """Return True when the path resolves to a known network filesystem type."""
        targetPath = shlex.quote(path)
        stdout, _, code = self._run_local(f'findmnt -n -o FSTYPE --target {targetPath}')
        if code != 0:
            return False

        fsType = stdout.strip().lower()
        if not fsType:
            return False

        return fsType in self.NETWORK_FILESYSTEM_TYPES or fsType.startswith('fuse.')

    def _is_in_integration_fixtures(self, path: str) -> bool:
        """Return True if path is under tests/integration/fixtures."""
        normalizedPath = os.path.normpath(os.path.abspath(path))
        return self.FIXTURE_PATH_FRAGMENT in normalizedPath

    def _stage_image_to_temp(self, sourcePath: str, imageSizeBytes: int) -> str:
        """Copy source image to OS temp directory and return staged path."""
        tmpFreeBytes = self._get_tmp_available_bytes()
        if tmpFreeBytes is not None and tmpFreeBytes < imageSizeBytes:
            raise RuntimeError(
                f"Insufficient free space in {tempfile.gettempdir()} for staging. "
                f"Required={self._format_bytes(imageSizeBytes)}, available={self._format_bytes(tmpFreeBytes)}"
            )

        fd, stagedPath = tempfile.mkstemp(prefix='os-config-image-', suffix='.img', dir=tempfile.gettempdir())
        os.close(fd)
        print(
            f"Staging image to local temp for mount: {sourcePath} -> {stagedPath} "
            f"({self._format_bytes(imageSizeBytes)})"
        )
        shutil.copy2(sourcePath, stagedPath)
        self._stagedImagePath = stagedPath
        return stagedPath

    def _cleanup_staged_image(self) -> None:
        """Remove staged image copy if one was created for this manager instance."""
        if not self._stagedImagePath:
            return

        stagedPath = self._stagedImagePath
        self._stagedImagePath = None
        try:
            if os.path.exists(stagedPath):
                os.remove(stagedPath)
        except OSError as e:
            print(f"Warning: Could not remove staged image {stagedPath}: {e}")

    def _confirm_stage_large_image(self, imageSizeBytes: int, memoryAvailableBytes: int | None,
                                   tmpFreeBytes: int | None) -> bool:
        """Prompt user to confirm staging large network-mounted images to temp."""
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(
                "Large network-mounted image detected, but no interactive terminal is available "
                "to confirm staging."
            )
            return False

        memoryText = self._format_bytes(memoryAvailableBytes) if memoryAvailableBytes is not None else 'unknown'
        tmpText = self._format_bytes(tmpFreeBytes) if tmpFreeBytes is not None else 'unknown'

        print("\nLarge image is on a network-mounted filesystem.")
        print(f"- Image size: {self._format_bytes(imageSizeBytes)}")
        print(f"- Available memory: {memoryText}")
        print(f"- Free space in {tempfile.gettempdir()}: {tmpText}")
        print("Staging copies the image to local temp before mounting.")

        while True:
            response = input("Proceed with local staging? [y/N]: ").strip().lower()
            if response in ('y', 'yes'):
                return True
            if response in ('', 'n', 'no'):
                return False
            print("Please respond with 'y' or 'n'.")

    @staticmethod
    def _get_available_memory_bytes() -> int | None:
        """Return MemAvailable bytes from /proc/meminfo when available."""
        try:
            with open('/proc/meminfo', 'r', encoding='utf-8') as memInfo:
                for line in memInfo:
                    if line.startswith('MemAvailable:'):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            return int(parts[1]) * 1024
        except OSError:
            return None
        return None

    @staticmethod
    def _get_tmp_available_bytes() -> int | None:
        """Return free bytes for OS temp directory."""
        try:
            return shutil.disk_usage(tempfile.gettempdir()).free
        except OSError:
            return None

    @staticmethod
    def _format_bytes(sizeBytes: int | None) -> str:
        """Format bytes to a compact human-readable string."""
        if sizeBytes is None:
            return 'unknown'

        value = float(sizeBytes)
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unitIndex = 0
        while value >= 1024 and unitIndex < len(units) - 1:
            value /= 1024
            unitIndex += 1
        return f"{value:.2f} {units[unitIndex]}"

class SDCardManager(BaseImageManager):
    """
    Execute operations on a mounted SD card via chroot with QEMU emulation.

    Handles block devices (SD cards, USB drives) with:
    - Robust partition detection using lsblk (supports all naming schemes)
    - Automatic reuse of existing mounts
    - Only unmounts partitions that this manager mounted
    - USB device auto-detection

    Prerequisites:
    - qemu-user-static must be installed on the host system
    - Block device must exist and contain Raspberry Pi OS partitions

    Examples:
        # Direct device path
        with SDCardManager(devicePath='/dev/sdb') as mgr:
            mgr.run('apt-get update', sudo=True)

        # Interactive USB device selection
        with SDCardManager.from_interactive_selection() as mgr:
            mgr.run('hostname')
    """

    def __init__(self, devicePath: str, mountPath: str = DEFAULT_MOUNT_PATH,
                 forceUnmount: bool = False, allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        """
        Initialize SDCardManager.

        Args:
            devicePath: Path to block device (e.g., /dev/sdb, /dev/mmcblk0)
            mountPath: Base path where filesystem will be mounted (default: DEFAULT_MOUNT_PATH)
            forceUnmount: If True, force-kill processes before unmounting (default: False)
            allowInteractiveSudo: Whether local sudo validation can prompt interactively.
            defaultChrootUser: Non-root user for chroot commands when ``sudo=False``.
            keepMounted: If True, skip automatic unmount during manager close.
        """
        self.devicePath = devicePath
        self._bootMountPath = None
        super().__init__(
            mountPath=mountPath,
            forceUnmount=forceUnmount,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
            keepMounted=keepMounted,
        )

    def _validate_target(self) -> None:
        """Validate device exists and is a block device"""
        if not os.path.exists(self.devicePath):
            raise ValueError(f"Device does not exist: {self.devicePath}")

        mode = os.stat(self.devicePath).st_mode
        if not stat.S_ISBLK(mode):
            raise ValueError(f"Not a block device: {self.devicePath}")

    def _perform_mount(self) -> None:
        """Mount SD card partitions, reusing existing mounts if available"""
        # Detect partitions using lsblk
        partitions = self._detect_partitions()

        if not partitions.get('root'):
            raise RuntimeError("Could not find root partition (ext4)")

        rootPartition = partitions['root']
        bootPartition = partitions.get('boot')

        # Check if root partition is already mounted
        if partitions.get('root_mountpoint'):
            print(f"Root partition already mounted at: {partitions['root_mountpoint']}")
            print(f"Reusing existing mount (will not unmount on cleanup)")
            self.mountPath = partitions['root_mountpoint']
            self._mountedByUs['root'] = False
        else:
            # Mount root partition
            mkdirResult = self._ensure_local_directory(self.mountPath, sudo=True)
            if mkdirResult.returnCode != 0:
                raise RuntimeError(f"Failed to create mount directory {self.mountPath}: {mkdirResult.stderr}")
            stdout, stderr, code = self._run_local(
                f'mount {rootPartition} {self.mountPath}',
                sudo=True
            )
            if code != 0:
                raise RuntimeError(f"Failed to mount root partition: {stderr}")
            print(f"Mounted root: {rootPartition} -> {self.mountPath}")
            self._mountedByUs['root'] = True

        # Handle boot partition
        if bootPartition:
            self._bootMountPath = os.path.join(self.mountPath, 'boot')

            if partitions.get('boot_mountpoint'):
                print(f"Boot partition already mounted at: {partitions['boot_mountpoint']}")
                # Check if it's mounted at the right place
                if partitions['boot_mountpoint'] == self._bootMountPath:
                    self._mountedByUs['boot'] = False
                else:
                    print(f"Warning: Boot already mounted elsewhere, not at {self._bootMountPath}")
                    self._mountedByUs['boot'] = False
            else:
                # Mount boot partition
                mkdirResult = self._ensure_local_directory(self._bootMountPath, sudo=True)
                if mkdirResult.returnCode != 0:
                    print(f"Warning: Failed to create boot mount directory: {mkdirResult.stderr}")
                    self._mountedByUs['boot'] = False
                else:
                    stdout, stderr, code = self._run_local(
                        f'mount {bootPartition} {self._bootMountPath}',
                        sudo=True
                    )
                    if code != 0:
                        print(f"Warning: Failed to mount boot partition: {stderr}")
                        self._mountedByUs['boot'] = False
                    else:
                        print(f"Mounted boot: {bootPartition} -> {self._bootMountPath}")
                        self._mountedByUs['boot'] = True

        # Apply ld.so.preload hack for apt-get support
        self._apply_ldpreload_hack()

    def _detect_partitions(self) -> dict:
        """
        Use lsblk to detect Raspberry Pi OS partitions with robust naming.

        Returns:
            {
                'root': '/dev/sdb2',  # or /dev/mmcblk0p2
                'boot': '/dev/sdb1',
                'root_mountpoint': '/media/user/rootfs' or None,
                'boot_mountpoint': '/media/user/boot' or None
            }
        """
        import json

        # Run lsblk with JSON output
        stdout, stderr, code = self._run_local(
            f'lsblk --json -o NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL {self.devicePath}'
        )

        if code != 0:
            raise RuntimeError(f"Failed to run lsblk: {stderr}")

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse lsblk output: {e}")

        result = {}

        # Navigate the lsblk JSON structure
        if 'blockdevices' in data and data['blockdevices']:
            device = data['blockdevices'][0]

            # Check if device has partitions (children)
            if 'children' in device:
                for partition in device['children']:
                    partName = partition.get('name', '')
                    fstype = partition.get('fstype', '')
                    mountpoint = partition.get('mountpoint')

                    # Identify boot partition (FAT32/vfat for Raspberry Pi)
                    if fstype in ['vfat', 'fat32', 'fat16']:
                        result['boot'] = f"/dev/{partName}"
                        result['boot_mountpoint'] = mountpoint

                    # Identify root partition (ext4 for Raspberry Pi)
                    elif fstype == 'ext4':
                        result['root'] = f"/dev/{partName}"
                        result['root_mountpoint'] = mountpoint

        return result

    @classmethod
    def detect_usb_devices(cls) -> list[dict]:
        """
        Detect removable USB storage devices.

        Returns:
            List of devices with info:
            [
                {
                    'device': '/dev/sdb',
                    'size': '8G',
                    'vendor': 'SanDisk',
                    'model': 'Ultra',
                    'label': 'RASPI_OS',
                    'mounted': True,
                    'mountpoints': ['/media/user/boot', '/media/user/rootfs']
                }
            ]
        """
        import json

        # Run lsblk to find USB removable devices
        result = subprocess.run(
            ['lsblk', '--json', '-o', 'NAME,SIZE,VENDOR,MODEL,TRAN,RM,LABEL,MOUNTPOINT,TYPE'],
            capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            print(f"Warning: Failed to run lsblk: {result.stderr}")
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        devices = []

        if 'blockdevices' in data:
            for device in data['blockdevices']:
                # Filter for removable USB devices (disk type)
                # Note: 'rm' can be boolean True or string '1' depending on lsblk version
                isRemovable = device.get('rm') in (True, '1', 1)

                if (device.get('type') == 'disk' and isRemovable and device.get('tran') == 'usb'):

                    # Collect mountpoints from partitions
                    mountpoints = []
                    if 'children' in device:
                        for child in device['children']:
                            mp = child.get('mountpoint')
                            if mp:
                                mountpoints.append(mp)

                    deviceInfo = {
                        'device': f"/dev/{device['name']}",
                        'size': device.get('size', 'Unknown'),
                        'vendor': (device.get('vendor', '') or 'Unknown').strip(),
                        'model': (device.get('model', '') or 'Unknown').strip(),
                        'label': device.get('label', ''),
                        'mounted': len(mountpoints) > 0,
                        'mountpoints': mountpoints
                    }
                    devices.append(deviceInfo)

        return devices

    @classmethod
    def from_interactive_selection(cls, mountPath: str = DEFAULT_MOUNT_PATH,
                                   allowInteractiveSudo: bool = True,
                                   defaultChrootUser: str | None = None) -> 'SDCardManager | None':
        """
        Interactively select a USB device and create an SDCardManager.

        Args:
            mountPath: Base path where filesystem will be mounted
            allowInteractiveSudo: Whether local sudo validation can prompt interactively.
            defaultChrootUser: Non-root user for chroot commands when ``sudo=False``.

        Returns:
            SDCardManager | None: Configured manager for selected device, or None if user aborts.
        """
        devices = cls.detect_usb_devices()

        if not devices:
            raise RuntimeError("No USB devices found")

        print("\n=== USB Devices Found ===")
        options = []
        for i, dev in enumerate(devices, 1):
            mountStatus = "mounted" if dev['mounted'] else "unmounted"
            mountInfo = f" at {', '.join(dev['mountpoints'])}" if dev['mountpoints'] else ""
            option = f"{dev['device']} - {dev['size']} {dev['vendor']} {dev['model']} [{mountStatus}{mountInfo}]"
            options.append(option)
            print(f"{i}. {option}")

        selectedIdx = get_user_selection(options, title="Select USB device:", addExit="Abort (back to main menu)")
        if selectedIdx is None:
            return None

        selectedDevice = devices[selectedIdx]

        # Confirmation
        print(f"\nSelected: {selectedDevice['device']} - {selectedDevice['size']} {selectedDevice['vendor']} {selectedDevice['model']}")
        confirmedIdx = get_user_selection(["No (back to main menu)", "Yes"], title="Confirm device selection?", addExit=False)
        if confirmedIdx != 1:
            return None

        return cls(
            devicePath=selectedDevice['device'],
            mountPath=mountPath,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
        )


def create_manager(mode: str, **kwargs) -> BaseManager:
    """Factory function to create the appropriate manager for a mode.

    Additional info (multi-line): this convenience function selects the
    correct manager implementation based on the ``mode`` argument and
    forwards any additional keyword arguments to the constructor.

    Args:
        mode (str): One of ``"local"``, ``"ssh"``, ``"image"``, or ``"sdcard"``.
        **kwargs: Additional arguments passed through to the manager
            constructor for the selected mode.

    Returns:
        BaseManager: An instance of ``LocalManager``, ``SSHManager``,
        ``ImageFileManager``, or ``SDCardManager`` depending on the mode.

    Examples:
        # Local execution
        mgr = create_manager('local')

        # Remote SSH
        mgr = create_manager('ssh', hostName='192.168.1.100', userName='pi',
                           keyFilename='/home/user/.ssh/id_rsa')

        # Image file
        mgr = create_manager('image', imagePath='/path/to/raspi.img')

        # SD card
        mgr = create_manager('sdcard', devicePath='/dev/sdb')

        # SD card with interactive selection
        mgr = create_manager('sdcard', interactive=True)
    """
    mode = mode.lower()

    if mode == 'local':
        return LocalManager()
    elif mode == 'ssh':
        return SSHManager(**kwargs)
    elif mode == 'image':
        return ImageFileManager(**kwargs)
    elif mode == 'sdcard':
        # Check for interactive mode
        if kwargs.get('interactive'):
            kwargs.pop('interactive')
            return SDCardManager.from_interactive_selection(**kwargs)
        return SDCardManager(**kwargs)
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'local', 'ssh', 'image', or 'sdcard'")


def interactive_create_manager() -> BaseManager | None:
    """Interactively create a manager using terminal menus.

    Returns:
        BaseManager | None: The created manager or None if cancelled.
    """
    options = ["Local (localhost)", "SSH (Remote)", "Image File", "SD Card"]

    while True:
        selectedModeIdx = get_user_selection(options, title="Select Manager Mode")
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

            sdCardSelectionModeIdx = get_user_selection(
                ["Auto-detect USB devices", "Enter device path manually"],
                title="SD Card Selection",
                addExit="Back to main menu"
            )

            if sdCardSelectionModeIdx is None:
                continue

            if sdCardSelectionModeIdx == 0:
                manager = SDCardManager.from_interactive_selection(
                    mountPath=DEFAULT_MOUNT_PATH
                )
                if manager is None:
                    continue
                return manager

            devicePath = input("Device Path (e.g., /dev/sdb): ").strip()
            while not devicePath:
                devicePath = input("Device Path (required): ").strip()

            mountPath = input(f"Mount Path [{DEFAULT_MOUNT_PATH}]: ").strip() or DEFAULT_MOUNT_PATH

            return create_manager('sdcard', devicePath=devicePath, mountPath=mountPath)



