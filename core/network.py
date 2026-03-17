#!/usr/bin/env python3
"""SSH operation stub for enabling/disabling SSH on target systems.

Additional info (multi-line): This module provides an Operation class that
follows the same operation-pipeline pattern as `hostname.py`. It resolves
configuration values from merged YAML, prompts for missing values, validates
the final config, and applies changes via a manager instance.

Usage:
    # Standalone - run as script
    python network.py            # Interactive operation menu (ssh)
    python network.py ssh        # Only manage SSH

    # Programmatic
    from lib.managers import create_manager
    from core.network import SSHOperation

    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        SSHOperation().execute(mgr)
"""
import sys
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline
# pylint: enable=wrong-import-position


class SSHOperation(OperationBase):
    """Operation class for enabling or disabling SSH on the target.

    The operation reads a single config key `ssh` which should be a string
    value of either `enabled` or `disabled`. If missing, the user is prompted
    interactively with the current state as the default.
    """

    SSH = 'ssh'
    REQUIRED_CONFIGS = {
        'type': 'boolean',  # Accept boolean True/False or strings 'enabled'/'disabled'
        'prompt': 'Enable SSH on target? (Y/n) (default: {default})',
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.SSH: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='network', name=self.SSH, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any]) -> dict[str, Any]:
        """
        Prompt for missing SSH config value.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        if self.SSH not in configsToPrompt:
            return {}

        currState = SSHOperation.get_current_ssh_state(mgr)
        prompt = self.REQUIRED_CONFIGS['prompt']
        raw = self._prompt_text_value(prompt, currState).strip()
        if not raw:
            return {self.SSH: currState}
        answer = SSHOperation._normalize_state(raw)
        return {self.SSH: answer}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """
        Apply SSH enable/disable change.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: SSH operation record.
        """
        newState = SSHOperation._normalize_state(configs[self.SSH])
        oldState = SSHOperation.get_current_ssh_state(mgr)
        return SSHOperation.set_ssh(mgr, oldState, newState)

    @staticmethod
    def get_current_ssh_state(mgr: BaseManager) -> str:
        """
        Determine whether SSH is currently enabled on the target.

        Args:
            mgr (BaseManager): Manager instance for command execution.

        Returns:
            str: `enabled` or `disabled`.
        """
        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        if isImage and isRaspi:
            if mgr.file_exists('/boot/ssh') or mgr.file_exists('/boot/firmware/ssh'):
                return 'enabled'
            return 'disabled'
            
        elif isImage and not isRaspi:
            if mgr.file_exists('/etc/systemd/system/multi-user.target.wants/ssh.service'):
                return 'enabled'
            return 'disabled'
            
        else:
            result = mgr.run('systemctl is-enabled ssh', sudo=False)
            if result.returnCode == 0 and 'enabled' in result.stdout:
                return 'enabled'
            
            status = mgr.run('systemctl is-active ssh', sudo=False)
            if status.returnCode == 0 and 'active' in status.stdout:
                return 'enabled'
                
            return 'disabled'

    @staticmethod
    def _normalize_state(val: Any) -> str:
        """Normalize boolean/string-like input to 'enabled' or 'disabled'.

        Accepts booleans, numbers, and common truthy/falsey strings.
        """
        # booleans
        if isinstance(val, bool):
            return 'enabled' if val else 'disabled'
        # numbers (non-zero => enabled)
        if isinstance(val, (int, float)):
            return 'enabled' if val != 0 else 'disabled'
        # strings
        s = str(val).strip().lower()
        if s in ('1', 'true', 'yes', 'y', 'enabled', 'on', 'active'):
            return 'enabled'
        if s in ('0', 'false', 'no', 'n', 'disabled', 'off', 'inactive'):
            return 'disabled'
        # default fallback to disabled
        return 'disabled'

    @staticmethod
    def set_ssh(mgr: BaseManager, oldState: str, newState: str) -> OperationLogRecord:
        """
        Enable or disable SSH on the target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            oldState (str): Current state (`enabled` or `disabled`).
            newState (str): Desired state (`enabled` or `disabled`).

        Returns:
            OperationLogRecord: SSH operation record.
        """
        currentState = oldState
        changed = False
        errors: list[str] = []

        if oldState == newState:
            print(f"SSH is already {newState}, no change needed.")
            return OperationLogRecord(SSHOperation.SSH, changed, oldState, currentState, errors)

        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()
        cmdResult = None
        
        if isImage and isRaspi:
            sshPath = '/boot/firmware/ssh' if mgr.dir_exists('/boot/firmware') else '/boot/ssh'
            if newState == 'enabled':
                cmdResult = mgr.run(f'touch {sshPath}', sudo=True)
            else:
                cmdResult = mgr.run(f'rm -f {sshPath}', sudo=True)
        
        elif isImage and not isRaspi:
            symlink = '/etc/systemd/system/multi-user.target.wants/ssh.service'
            target = '/lib/systemd/system/ssh.service'
            if newState == 'enabled':
                cmdResult = mgr.run(f'ln -s {target} {symlink}', sudo=True)
            else:
                cmdResult = mgr.run(f'rm -f {symlink}', sudo=True)
                
        elif not isImage and isRaspi:
            arg = 0 if newState == 'enabled' else 1
            cmdResult = mgr.run(f'raspi-config nonint do_ssh {arg}', sudo=True)
            
        else:
            if newState == 'enabled':
                cmdResult = mgr.run('systemctl enable --now ssh', sudo=True)
            else:
                cmdResult = mgr.run('systemctl disable --now ssh', sudo=True)

        if cmdResult and cmdResult.returnCode == 0:
            verified = SSHOperation.get_current_ssh_state(mgr)
            if verified == newState:
                changed = True
                currentState = verified
                print(f"Set SSH state: {oldState} -> {newState}")
            else:
                errMsg = f'SSH state verification failed: expected {newState}, got {verified}'
                errors.append(errMsg)
                print(errMsg)
        else:
            stderr = cmdResult.stderr if cmdResult else "No command executed"
            errMsg = stderr.strip() if stderr.strip() else f'Failed to set SSH state to {newState}'
            errors.append(errMsg)
            print(f"Error setting SSH state: {stderr}")

        return OperationLogRecord(SSHOperation.SSH, changed, oldState, currentState, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([SSHOperation()])
    pipeline.run_cli('Configure network settings (SSH)')
