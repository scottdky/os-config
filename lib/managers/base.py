"""Base manager abstractions and shared host-side helpers."""

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from types import TracebackType
from typing import Any

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


class CommandExecutionError(RuntimeError):
    """Raised when a command returns a non-zero exit status.

    Args:
        command (str): Command that was executed.
        sudo (bool): Whether command executed with elevated privileges.
        commandResult (CommandResult): Result payload from command execution.
        errorPrefix (str | None): Optional context prefix for the message.
    """

    def __init__(self, command: str, sudo: bool, commandResult: CommandResult, errorPrefix: str | None = None) -> None:
        stderr = commandResult.stderr.strip()
        prefix = f'{errorPrefix}: ' if errorPrefix else ''
        message = (
            f"{prefix}Command failed (code={commandResult.returnCode}, sudo={sudo}): {command}"
            f"{f'\n{stderr}' if stderr else ''}"
        )
        super().__init__(message)
        self.command = command
        self.sudo = sudo
        self.commandResult = commandResult


class BaseManager:
    """Base class defining the common interface for all managers"""

    def __init__(self, allowInteractiveSudo: bool = True) -> None:
        """Initialize shared manager state.

        Args:
            allowInteractiveSudo (bool): Default policy for whether local sudo
                validation may prompt interactively via ``sudo -v``.
        """
        self.allowInteractiveSudo = allowInteractiveSudo
        self._operationLogs: list[Any] = []
        self._backed_up_files: set[str] = set()

    def is_raspi_os(self) -> bool:
        """Check if the target is running Raspberry Pi OS.

        In 32-bit systems os-release will show Raspian, but on 64-bit systems
        every key is Debian, including the URL. Therefore, we check for
        what we really care about: the presence of raspi-config, which is
        unique to Raspberry Pi OS.
        """
        return self.exists('/usr/bin/raspi-config')

    def is_os_image(self) -> bool:
        """Check if the target is an OS image (img file or sdcard)"""
        return False # Default to False; override in relevant manager subclasses

    def get_boot_file_path(self, fname: str) -> str:
        """
        Get the correct path to a Raspberry Pi boot configuration file (e.g., config.txt or cmdline.txt).

        Additional info (multi-line): In Debian Bookworm and later, the boot partition is
        mounted at /boot/firmware. In older versions (like Bullseye), it was at /boot.

        Args:
            fname (str): The filename to search for (e.g., 'config.txt', 'cmdline.txt')

        Returns:
            str: The exact path to the target's active config file.

        Raises:
            FileNotFoundError: If the file cannot be found in known locations.
        """
        if self.exists(f'/boot/firmware/{fname}'):
            return f'/boot/firmware/{fname}'
        if self.exists(f'/boot/{fname}'):
            return f'/boot/{fname}'

        raise FileNotFoundError(f"Could not locate Raspberry Pi {fname} in /boot/firmware or /boot")

    def systemd_unmask(self, serviceName: str, sudo: bool = False) -> bool:
        """Unmask a systemd service.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        res = self.run(f"systemctl unmask {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_mask(self, serviceName: str, sudo: bool = False) -> bool:
        """Mask a systemd service.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        res = self.run(f"systemctl mask {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_enable(self, serviceName: str, servicePath: str | None = None, targetName: str = "sysinit.target", now: bool = False, sudo: bool = False) -> bool:
        """Enable a systemd service by name.

        Note: The BaseManager implementation uses systemctl. Subclasses (like offline ImageManager) may override this to use file links directly.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            servicePath (str | None): Absolute target path of the unit file (used by offline overrides).
            targetName (str): Systemd target to hook into. (used by offline overrides).
            now (bool): Whether to pass --now to start the service immediately.
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        nowFlag = " --now" if now else ""
        res = self.run(f"systemctl enable{nowFlag} {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_disable(self, serviceName: str, targetName: str = "sysinit.target", now: bool = False, sudo: bool = False) -> bool:
        """Disable a systemd service by name.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            targetName (str): Systemd target it hooks into. (used by offline overrides).
            now (bool): Whether to pass --now to stop the service immediately.
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        nowFlag = " --now" if now else ""
        res = self.run(f"systemctl disable{nowFlag} {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_is_enabled(self, serviceName: str, sudo: bool = False) -> bool:
        """Check if a systemd service is enabled.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the service is enabled.
        """
        res = self.run(f"systemctl is-enabled {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_is_active(self, serviceName: str, sudo: bool = False) -> bool:
        """Check if a systemd service is currently active.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the service is active.
        """
        res = self.run(f"systemctl is-active {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def is_pkg_installed(self, name: str) -> bool:
        """Check if a Debian package is currently installed."""
        res = self.run(f"dpkg-query -W -f='${{Status}}' {shlex.quote(name)} 2>/dev/null", sudo=False)
        return "install ok installed" in res.stdout

    def install_pkg(self, name: str) -> bool:
        """Installs a Debian package if it is not already installed.

        Args:
            name (str): Name of the package to install.

        Returns:
            bool: True if the package was newly installed, False if it was already present.

        Raises:
            RuntimeError: If the underlying installation command fails.
        """
        if self.is_pkg_installed(name):
            return False
        res = self.run(f"DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(name)}", sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to install package {name}: {res.stderr}")
        return True

    def remove_pkg(self, name: str, purge: bool = False) -> bool:
        """Removes a Debian package if it is currently installed.

        Args:
            name (str): Name of the package to remove.
            purge (bool): Whether to purge configuration files.

        Returns:
            bool: True if the package was removed, False if it was not installed.

        Raises:
            RuntimeError: If the underlying removal command fails.
        """
        if not self.is_pkg_installed(name):
            return False
        purgeFlag = "--purge " if purge else ""
        res = self.run(f"DEBIAN_FRONTEND=noninteractive apt-get remove -y {purgeFlag}{shlex.quote(name)}", sudo=True)
        if res.returnCode != 0:
            raise RuntimeError(f"Failed to remove package {name}: {res.stderr}")
        return True

    def log_operation(self, operationRecord: Any) -> None:
        """Append one operation record to manager-owned operation logs.

        Args:
            operationRecord (object): Structured operation result payload.
        """
        self._operationLogs.append(operationRecord)

    def get_operation_logs(self) -> list[Any]:
        """Return a shallow copy of accumulated operation logs.

        Returns:
            list[object]: Operation records in insertion order.
        """
        return list(self._operationLogs)

    def clear_operation_logs(self) -> None:
        """Clear accumulated operation logs for a fresh pipeline run."""
        self._operationLogs.clear()

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

    def run_or_raise(self, command: str, sudo: bool = False, errorPrefix: str | None = None) -> CommandResult:
        """Execute a command and raise when the exit status is non-zero.

        Additional info (multi-line): this provides a concise exception-style
        flow for operation code that otherwise repeats return-code checks.

        Args:
            command (str): Command to execute.
            sudo (bool): Whether to run with elevated privileges.
            errorPrefix (str | None): Optional message prefix for raised errors.

        Returns:
            CommandResult: Successful command result.

        Raises:
            CommandExecutionError: Command returned a non-zero exit status.
        """
        commandResult = self.run(command, sudo=sudo)
        if commandResult.returnCode != 0:
            raise CommandExecutionError(command, sudo, commandResult, errorPrefix)
        return commandResult

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
        commandResult = self.run(f'cat {remotePath}', sudo=sudo)
        return commandResult.stdout if commandResult.returnCode == 0 else ''

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

    def backup_file(self, remotePath: str, backupExt: str = '.bak', sudo: bool = False) -> None:
        """Create a backup of a file if it hasn't been backed up yet during this run.

        Additional info (multi-line): To prevent sequential operations from overwriting
        the original pristine backup with intermediate modified states, this method
        tracks backed-up files in a set and only creates the backup once per file path.

        Args:
            remotePath (str): Path to the target file.
            backupExt (str): Backup extension to append to the filename.
            sudo (bool): Whether to use elevated privileges.
        """
        if not backupExt or remotePath in self._backed_up_files or not self.exists(remotePath):
            return

        existing_content = self.read_file(remotePath, sudo=sudo)
        backupPath = f"{remotePath}{backupExt}"
        self.write_file(backupPath, existing_content, sudo=sudo)
        self._backed_up_files.add(remotePath)

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

        existing_content = ''
        if self.exists(remotePath):
            existing_content = self.read_file(remotePath, sudo=sudo)

        existing_lines = existing_content.splitlines()
        modified = False

        for line in lines_to_add:
            if line in existing_lines:
                continue

            escape_line = re.escape(line)
            pattern = re.compile(r'^\s*#\s*' + escape_line + r'\s*$')

            found_commented = False
            for i, existing_line in enumerate(existing_lines):
                if pattern.match(existing_line):
                    existing_lines[i] = line
                    modified = True
                    found_commented = True
                    #print(f"Uncommented line in {remotePath}: {line.strip()[:50]}...")
                    break

            if found_commented:
                continue

            existing_lines.append(line)
            modified = True
            #print(f"Appended to {remotePath}: {line.strip()[:50]}...")

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
            pass #print(f"No changes made to {remotePath}")

    def sed(self, remotePath: str, before: str, after: str, useRegex: bool = False,
            limit: int = 0, backup: str = '.bak', sudo: bool = False) -> None:
        """Perform in-place search and replace on a file (like sed -i)."""
        if not self.exists(remotePath):
            #print(f"File not found: {remotePath}")
            return

        existing_content = self.read_file(remotePath, sudo=sudo)
        if not existing_content:
            #print(f"Could not read file: {remotePath}")
            return

        if useRegex:
            newContent = re.sub(before, after, existing_content, count=0 if limit == 0 else limit)
        else:
            if limit == 0:
                newContent = existing_content.replace(before, after)
            else:
                newContent = existing_content.replace(before, after, limit)

        if newContent == existing_content:
            #print(f"No changes made to {remotePath} (pattern not found)")
            return

        if backup:
            self.backup_file(remotePath, backupExt=backup, sudo=sudo)

        fd, tempPath = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(newContent)
            self.put(tempPath, remotePath, sudo=sudo)
            #print(f"Modified {remotePath}")
        finally:
            if os.path.exists(tempPath):
                os.remove(tempPath)

    def set_config_line(self, remotePath: str, line: str, enable: bool = True, backup: str = '.bak', sudo: bool = False) -> bool:
        """
        Enables or disables a configuration line in a file by commenting / uncommenting.

        Additional info (multi-line): This intelligently looks for the exact line (ignoring leading/trailing
        whitespace and comment characters) and sets it to the desired state. If enable is True and the line
        is missing, it will be added. If enable is False and the line is missing, no action is taken.

        Args:
            remotePath (str): Path to the target file.
            line (str): The configuration line to manage (without comments, e.g. 'dtparam=spi=on').
            enable (bool): True to uncomment/add the line, False to comment it out.
            backup (str): Backup extension to use before modifying, or empty to skip backing up.
            sudo (bool): Whether to use elevated privileges.

        Returns:
            bool: True if a change was made, False if the line was already in the desired state or file didn't exist when trying to disable.
        """
        if not self.exists(remotePath):
            if not enable:
                return False
            existing_content = ''
        else:
            existing_content = self.read_file(remotePath, sudo=sudo)

        existing_lines = existing_content.splitlines() if existing_content else []
        modified = False

        escape_line = re.escape(line.strip())
        pattern = re.compile(r'^\s*#?\s*' + escape_line + r'\s*$')

        found = False
        target_line = line.strip() if enable else f"#{line.strip()}"

        for i, existing_line in enumerate(existing_lines):
            if pattern.match(existing_line):
                found = True
                if existing_lines[i].strip() != target_line:
                    existing_lines[i] = target_line
                    modified = True
                break

        if not found and enable:
            existing_lines.append(target_line)
            modified = True

        if modified:
            if backup:
                self.backup_file(remotePath, backupExt=backup, sudo=sudo)

            new_content = '\n'.join(existing_lines) + '\n'
            self.write_file(remotePath, new_content, sudo=sudo)

        return modified

    def run_local(self, command: str, sudo: bool = False,
                allowInteractiveSudo: bool | None = None) -> CommandResult:
        """Run a shell command on the host system."""
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
        """Validate local sudo availability for privileged host commands."""
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
        """Ensure a host-side directory exists."""
        if not path:
            return CommandResult('', 'Directory path is required', 1)

        if sudo:
            return self.run_local(f'mkdir -p {shlex.quote(path)}', sudo=True)

        try:
            os.makedirs(path, exist_ok=True)
            return CommandResult('', '', 0)
        except Exception as e:
            return CommandResult('', str(e), 1)

    def _remove_local_directory(self, path: str, sudo: bool = False) -> CommandResult:
        """Remove a host-side directory if it exists and is empty."""
        if not path or not os.path.exists(path):
            return CommandResult('', '', 0)

        if sudo:
            return self.run_local(f'rmdir {shlex.quote(path)}', sudo=True)

        try:
            os.rmdir(path)
            return CommandResult('', '', 0)
        except Exception as e:
            return CommandResult('', str(e), 1)

    def _put_local(self, localPath: str, remotePath: str, sudo: bool = False,
                   base_dir: str | None = None, ensure_dir_when_not_sudo: bool = False,
                   label: str | None = None) -> None:
        """Helper for local-style copy (localhost or chroot filesystem)."""
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
                        #print(f"Error creating destination directory{context}: {mkdirResult.stderr}")
                        return

            if sudo:
                _, stderr, code = self.run_local(
                    f'cp {shlex.quote(localPath)} {shlex.quote(destPath)}',
                    sudo=True
                )
                if code != 0:
                    context = f" {label}" if label else ''
                    #print(f"Error copying file{context}: {stderr}")
                    return
            else:
                shutil.copy2(localPath, destPath)

            suffix = f" ({label})" if label else ''
            # print(f"Copied {localPath} -> {remotePath}{suffix}")
        except Exception as e:
            context = f" {label}" if label else ''
            # Return a CommandResult for consistency with other exception handlers
            return CommandResult('', f"Error copying file{context}: {e}", 1)

    def close(self) -> None:
        """Clean up resources"""
        return

    def __enter__(self) -> "BaseManager":
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self.close()


__all__ = ['DEFAULT_MOUNT_PATH', 'CommandResult', 'CommandExecutionError', 'BaseManager']
