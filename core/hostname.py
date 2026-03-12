#CMD: hostname setup Name & Pass

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
from lib.operations import OperationBase, OperationPipeline
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

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any]) -> dict[str, Any]:
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

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> bool:
        """Apply hostname change.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            bool: True if hostname changed.
        """
        newName = configs.get(self.HOSTNAME)
        if not newName:
            return False
        return self.set_host(mgr, str(newName))

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
    def set_host(mgr: BaseManager, newName: str) -> bool:
        """Set the hostname on the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            newName (str): The new hostname to set.

        Returns:
            bool: True if hostname was changed, False if already set.
        """
        oldName = HostnameOperation.get_current_hostname(mgr)
        if oldName == newName:
            print(f"Hostname is already {newName}, no change needed.")
            return False

        mgr.sed('/etc/hostname', oldName, newName, sudo=True)
        mgr.sed('/etc/hosts', oldName, newName, sudo=True)
        print(f"Changed hostname from {oldName} to {newName}")
        return True


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

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any]) -> dict[str, Any]:
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

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> bool:
        """Apply username change.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            bool: True if username changed.
        """
        newUser = configs.get(self.USERNAME)
        if not newUser:
            return False

        oldUser = self.get_current_user(mgr)
        return self.set_user(mgr, oldUser, str(newUser))

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
    def set_user(mgr: BaseManager, oldUser: str, newUser: str) -> bool:
        """Rename a user account on the target system.

        Additional info (multi-line): changes the username and home directory.
        Note that the user should not be logged in when this is run.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            oldUser (str): Current username to rename.
            newUser (str): New username.

        Returns:
            bool: True if user was renamed successfully, False otherwise.
        """
        _, stderr, code = mgr.run(f'usermod -m -l {newUser} -d /home/{newUser} {oldUser}', sudo=True)
        if code == 0:
            print(f"Renamed user from {oldUser} to {newUser}")
            return True

        print(f"Error renaming user: {stderr}")
        return False


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

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any]) -> dict[str, Any]:
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

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> bool:
        """Apply password change for current user.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            bool: True if password changed.
        """
        password = configs.get(self.PASSWORD)
        if not password:
            return False

        targetUserName = UsernameOperation.get_current_user(mgr)
        return self.set_pass(mgr, targetUserName, str(password))

    @staticmethod
    def set_pass(mgr: BaseManager, userName: str, password: str) -> bool:
        """Set password for a user on the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            userName (str): Username to change password for.
            password (str): The password to set (plaintext).

        Returns:
            bool: True if password was changed, False otherwise.
        """
        _, stderr, code = mgr.run(f"echo '{userName}:{password}' | chpasswd", sudo=True)
        if code == 0:
            print(f"Password changed for user {userName}")
            return True

        print(f"Error changing password: {stderr}")
        return False


if __name__ == '__main__':
    pipeline = OperationPipeline([HostnameOperation(), UsernameOperation(), PasswordOperation()])
    sys.exit(pipeline.run_cli('Configure hostname, username, and password'))
