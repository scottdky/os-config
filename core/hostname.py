#!/usr/bin/env python3
"""Set hostname, username, and password using operation classes.

Additional info (multi-line): this module follows the operation pipeline
architecture. Each operation class resolves config values from the merged YAML
configuration, prompts for missing values, validates final config, and applies
changes through a shared manager context.

Usage:
    # Standalone - run as script
    python hostname.py              # Interactive operation menu (hostname/username/password/all)
    python hostname.py hostname     # Only set hostname
    python hostname.py username     # Only set username
    python hostname.py password     # Only set password

    # Programmatic
    from lib.managers import create_manager
    from core.hostname import HostnameOperation

    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        HostnameOperation().execute(mgr)

Configuration:
    Add to config.yaml:
    hostname:
        hostname: newhost      # if missing, prompt with current hostname default
        username: newuser      # if missing, prompt with current username default
        password: s3cr3t       # if missing, secure prompt is required
"""
import sys
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline
# pylint: enable=wrong-import-position


class HostnameOperation(OperationBase):
    """Operation class for setting hostname."""

    HOSTNAME = 'hostname'
    REQUIRED_CONFIGS = {
        'type': 'str',
        'prompt': 'Enter new hostname (press Enter to keep default: {default})',
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.HOSTNAME: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='hostname', name=self.HOSTNAME, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing hostname value.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        if self.HOSTNAME not in configsToPrompt:
            return {}

        currHost = self.get_current_hostname(mgr)
        prompt = self.REQUIRED_CONFIGS['prompt']
        hostName = self._prompt_text_value(prompt, currHost).strip()
        return {self.HOSTNAME: hostName if hostName else currHost}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply hostname change.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Hostname operation record.
        """
        newName = str(configs[self.HOSTNAME])
        return HostnameOperation.set_host(mgr, newName)

    @staticmethod
    def get_current_hostname(mgr: BaseManager) -> str:
        """Get current hostname from target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.

        Returns:
            str: Current hostname, or empty string if unavailable.
        """
        hostNameResult = mgr.run('cat /etc/hostname', sudo=False)
        if hostNameResult.returnCode == 0:
            return hostNameResult.stdout.strip()
        return ''

    @staticmethod
    def set_host(mgr: BaseManager, newName: str) -> OperationLogRecord:
        """Set the hostname on the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            newName (str): The new hostname to set.

        Returns:
            OperationLogRecord: Hostname operation record.
        """
        oldName = HostnameOperation.get_current_hostname(mgr)
        currentName = oldName
        changed = False
        errors: list[str] = []

        if oldName == newName:
            print(f"Hostname is already {newName}, no change needed.")
            return OperationLogRecord(HostnameOperation.HOSTNAME, changed, oldName, currentName, errors)

        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        if isImage:
            # For offline images, directly edit the files
            mgr.sed('/etc/hostname', oldName, newName, sudo=True)
            mgr.sed('/etc/hosts', oldName, newName, sudo=True)
        elif not isImage and isRaspi:
            # Use raspi-config for live Pi
            mgr.run(f'raspi-config nonint do_hostname {newName}', sudo=True)
        else:
            # Use hostnamectl for live Debian
            mgr.run(f'hostnamectl set-hostname {newName}', sudo=True)
            # Ensure /etc/hosts is also updated to prevent resolution issues
            mgr.sed('/etc/hosts', oldName, newName, sudo=True)

        currentName = HostnameOperation.get_current_hostname(mgr)
        if currentName == newName:
            changed = True
            print(f"Changed hostname from {oldName} to {newName}")
        else:
            errMsg = f'Hostname update verification failed: expected {newName}, got {currentName}'
            errors.append(errMsg)
            print(errMsg)

        return OperationLogRecord(HostnameOperation.HOSTNAME, changed, oldName, currentName, errors)


class UsernameOperation(OperationBase):
    """Operation class for setting username."""

    USERNAME = 'username'
    REQUIRED_CONFIGS = {
        'type': 'str',
        'prompt': 'Enter new username (press Enter to keep default: {default})',
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.USERNAME: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='hostname', name=self.USERNAME, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing username value.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        if self.USERNAME not in configsToPrompt:
            return {}

        currUser = self.get_current_user(mgr)
        prompt = self.REQUIRED_CONFIGS['prompt']
        userName = self._prompt_text_value(prompt, currUser).strip()
        return {self.USERNAME: userName if userName else currUser}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply username change.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Username operation record.
        """
        newUser = str(configs[self.USERNAME])
        oldUser = self.get_current_user(mgr)
        return UsernameOperation.set_user(mgr, oldUser, newUser)

    @staticmethod
    def get_current_user(mgr: BaseManager) -> str:
        """Get the first non-root user from the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.

        Returns:
            str: Username (defaults to 'pi' if unable to determine).
        """
        userListResult = mgr.run("getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'", sudo=False)
        if userListResult.returnCode == 0 and userListResult.stdout.strip():
            return userListResult.stdout.strip().split('\n')[0]
        return 'pi'

    @staticmethod
    def set_user(mgr: BaseManager, oldUser: str, newUser: str) -> OperationLogRecord:
        """Rename a user account on the target system.

        Additional info (multi-line): changes the username and home directory.
        Note that the user should not be logged in when this is run.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            oldUser (str): Current username to rename.
            newUser (str): New username.

        Returns:
            OperationLogRecord: Username operation record.
        """
        currentUser = oldUser
        changed = False
        errors: list[str] = []

        if oldUser == newUser:
            print(f"Username is already {newUser}, no change needed.")
        else:
            commandResult = mgr.run(f'usermod -m -l {newUser} -d /home/{newUser} {oldUser}', sudo=True)
            if commandResult.returnCode == 0:
                print(f"Renamed user from {oldUser} to {newUser}")
                changed = True
                currentUser = newUser
            else:
                stderr = commandResult.stderr
                errMsg = stderr.strip() if stderr.strip() else f'Failed to rename user {oldUser} -> {newUser}'
                errors.append(errMsg)
                print(f"Error renaming user: {stderr}")

        return OperationLogRecord(UsernameOperation.USERNAME, changed, oldUser, currentUser, errors)


class PasswordOperation(OperationBase):
    """Operation class for setting password."""

    PASSWORD = 'password'
    REQUIRED_CONFIGS = {
        'type': 'str',
        'prompt': 'Enter password for user',
        'secure': True,
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.PASSWORD: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='hostname', name=self.PASSWORD, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing password value.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        _ = mgr
        if self.PASSWORD not in configsToPrompt:
            return {}

        prompt = self.REQUIRED_CONFIGS['prompt']
        password = self._prompt_secure_value(prompt)
        return {self.PASSWORD: password}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply password change for current user.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Password operation record.
        """
        password = str(configs[self.PASSWORD])
        targetUserName = UsernameOperation.get_current_user(mgr)
        return PasswordOperation.set_pass(mgr, targetUserName, password)

    @staticmethod
    def set_pass(mgr: BaseManager, userName: str, password: str) -> OperationLogRecord:
        """Set password for a user on the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            userName (str): Username to change password for.
            password (str): The password to set (plaintext).

        Returns:
            OperationLogRecord: Password operation record.
        """
        previousState = {'userName': userName, 'password': '<redacted>'}
        currentState = {'userName': userName, 'password': '<redacted>'}
        changed = False
        errors: list[str] = []

        commandResult = mgr.run(f"echo '{userName}:{password}' | chpasswd", sudo=True)
        if commandResult.returnCode == 0:
            print(f"Password changed for user {userName}")
            changed = True
            currentState = {'userName': userName, 'password': '<updated>'}
        else:
            stderr = commandResult.stderr
            errMsg = stderr.strip() if stderr.strip() else f'Failed to update password for user {userName}'
            errors.append(errMsg)
            print(f"Error changing password: {stderr}")

        return OperationLogRecord(PasswordOperation.PASSWORD, changed, previousState, currentState, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([HostnameOperation(), UsernameOperation(), PasswordOperation()])
    pipeline.run_cli('Configure hostname, username, and password')
