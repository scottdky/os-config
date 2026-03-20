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
import shlex
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

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
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
            if mgr.exists('/boot/ssh') or mgr.exists('/boot/firmware/ssh'):
                return 'enabled'
            return 'disabled'

        elif isImage and not isRaspi:
            if mgr.exists('/etc/systemd/system/multi-user.target.wants/ssh.service'):
                return 'enabled'
            return 'disabled'

        else:
            if mgr.systemd_is_enabled('ssh', sudo=False):
                return 'enabled'

            if mgr.systemd_is_active('ssh', sudo=False):
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
            sshPath = '/boot/firmware/ssh' if mgr.exists('/boot/firmware') else '/boot/ssh'
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
                success = mgr.systemd_enable('ssh', now=True, sudo=True)
            else:
                success = mgr.systemd_disable('ssh', now=True, sudo=True)

            # Form dummy command result for following check block
            cmdResult = type('obj', (object,), {'returnCode': 0 if success else 1, 'stderr': 'systemd manager action failed'})()

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


class WiFiOperation(OperationBase):
    """Operation class for configuring Wi-Fi on the target.

    Sets the Wi-Fi country code and optionally configures an SSID and password.
    """

    WIFI = 'wifi'
    REQUIRED_CONFIGS = {
        'wifi_country': {
            'type': 'str',
            'prompt': 'Enter Wi-Fi Country Code (e.g. US, GB) (press Enter to keep default: {default})',
        },
        'wifi_ssid': {
            'type': 'str',
            'prompt': 'Enter Wi-Fi SSID (press Enter to keep default: {default})',
        },
        'wifi_password': {
            'type': 'password',
            'prompt': 'Enter Wi-Fi Password (leave empty for none): ',
        }
    }

    def __init__(self) -> None:
        super().__init__(moduleName='network', name=self.WIFI, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing Wi-Fi config values."""
        results = {}

        if 'wifi_country' in configsToPrompt:
            currCountry = WiFiOperation.get_current_wifi_country(mgr)
            prompt = self.REQUIRED_CONFIGS['wifi_country']['prompt']
            ans = self._prompt_text_value(prompt, currCountry).strip()
            results['wifi_country'] = ans if ans else currCountry

        if 'wifi_ssid' in configsToPrompt:
            currSsid = WiFiOperation.get_current_wifi_ssid(mgr)
            prompt = self.REQUIRED_CONFIGS['wifi_ssid']['prompt']
            ans = self._prompt_text_value(prompt, currSsid).strip()
            results['wifi_ssid'] = ans if ans else currSsid

        if 'wifi_password' in configsToPrompt:
            prompt = self.REQUIRED_CONFIGS['wifi_password']['prompt']
            import getpass
            ans = getpass.getpass(prompt).strip()
            results['wifi_password'] = ans

        return results

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply Wi-Fi changes."""
        country = str(configs.get('wifi_country', ''))
        ssid = str(configs.get('wifi_ssid', ''))
        password = str(configs.get('wifi_password', ''))

        oldCountry = WiFiOperation.get_current_wifi_country(mgr)
        oldState = f"Country: {oldCountry}"

        return WiFiOperation.set_wifi(mgr, country, ssid, password, oldState)

    @staticmethod
    def get_current_wifi_country(mgr: BaseManager) -> str:
        """Get current Wi-Fi country code."""
        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        if isImage and isRaspi:
            # Check for wpa_supplicant conf on boot drive
            bootDir = '/boot/firmware' if mgr.exists('/boot/firmware') else '/boot'
            wpaConf = f"{bootDir}/wpa_supplicant.conf"
            res = mgr.run(f"grep '^country=' {wpaConf}", sudo=True)
            if res.returnCode == 0 and res.stdout.strip():
                return res.stdout.strip().split('=')[1].strip()
            return ''
        elif not isImage and isRaspi:
            res = mgr.run('raspi-config nonint get_wifi_country', sudo=True)
            if res.returnCode == 0:
                return res.stdout.strip()
            return ''
        elif not isImage and not isRaspi:
            res = mgr.run('iw reg get | grep "country" | head -n 1', sudo=True)
            if res.returnCode == 0 and res.stdout.strip():
                # E.g. "country US: DFS-FCC"
                return res.stdout.strip().split()[1].replace(':', '')
            return ''
        else:
            # Debian Image - usually not managed without boot provisioning or proper NM setup
            # Just read from WPA if exists
            res = mgr.run('grep "^country=" /etc/wpa_supplicant/wpa_supplicant.conf', sudo=True)
            if res.returnCode == 0 and res.stdout.strip():
                return res.stdout.strip().split('=')[1].strip()
            return ''

    @staticmethod
    def get_current_wifi_ssid(mgr: BaseManager) -> str:
        """Attempt to get current Wi-Fi SSID (best-effort)."""
        res = mgr.run('iwgetid -r', sudo=False)
        if res.returnCode == 0:
            return res.stdout.strip()
        return ''

    @staticmethod
    def set_wifi(mgr: BaseManager, country: str, ssid: str, password: str, oldState: str) -> OperationLogRecord:
        """Set Wi-Fi configuration."""
        changed = False
        errors: list[str] = []
        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        try:
            if isImage and isRaspi:
                # Write to /boot/wpa_supplicant.conf for Pi auto-provisioning
                bootDir = '/boot/firmware' if mgr.exists('/boot/firmware') else '/boot'
                confPath = f"{bootDir}/wpa_supplicant.conf"

                content = f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\\nupdate_config=1\\ncountry={country}\\n"
                if ssid:
                    content += f"\\nnetwork={{\\n    ssid=\"{ssid}\"\\n"
                    if password:
                        content += f"    psk=\"{password}\"\\n"
                    else:
                        content += "    key_mgmt=NONE\\n"
                    content += "}\\n"

                mgr.run_or_raise(f"printf '%b' {shlex.quote(content)} > {confPath}", sudo=True, errorPrefix='Failed to create wpa_supplicant.conf')
                changed = True

            elif isImage and not isRaspi:
                # Debian image - Use NetworkManager pre-provisioning
                if ssid:
                    connPath = f"/etc/NetworkManager/system-connections/{ssid}.nmconnection"
                    content = f"[connection]\\nid={ssid}\\ntype=wifi\\n\\n[wifi]\\nssid={ssid}\\n"
                    if password:
                        content += f"\\n[wifi-security]\\nkey-mgmt=wpa-psk\\npsk={password}\\n"

                    mgr.run_or_raise(f"printf '%b' {shlex.quote(content)} > {connPath}", sudo=True, errorPrefix='Failed to create nmconnection')
                    mgr.run_or_raise(f"chmod 600 {connPath}", sudo=True, errorPrefix='Failed to set nmconnection permissions')
                    changed = True

            elif not isImage and isRaspi:
                # Live Pi
                if country:
                    mgr.run_or_raise(f"raspi-config nonint do_wifi_country {shlex.quote(country)}", sudo=True, errorPrefix='Failed to set Pi Wi-Fi country')
                    changed = True
                if ssid:
                    cmd = f"raspi-config nonint do_wifi_ssid_passphrase {shlex.quote(ssid)} {shlex.quote(password)}"
                    mgr.run_or_raise(cmd, sudo=True, errorPrefix='Failed to set Pi Wi-Fi credentials')
                    changed = True

            elif not isImage and not isRaspi:
                # Live Debian
                if country:
                    mgr.run_or_raise(f"iw reg set {shlex.quote(country)}", sudo=True, errorPrefix='Failed to set Debian Wi-Fi country')
                    changed = True
                if ssid:
                    if password:
                        cmd = f"nmcli device wifi connect {shlex.quote(ssid)} password {shlex.quote(password)}"
                    else:
                        cmd = f"nmcli device wifi connect {shlex.quote(ssid)}"
                    mgr.run_or_raise(cmd, sudo=True, errorPrefix='Failed to set Debian Wi-Fi credentials')
                    changed = True

        except Exception as e:
            errors.append(str(e))
            print(f"Error configuring Wi-Fi: {e}")

        newCountry = WiFiOperation.get_current_wifi_country(mgr)
        newState = f"Country: {newCountry}, SSID: {ssid}"

        return OperationLogRecord(WiFiOperation.WIFI, changed, oldState, newState, errors)

if __name__ == '__main__':
    pipeline = OperationPipeline([SSHOperation(), WiFiOperation()])
    pipeline.run_cli('Configure network settings (SSH, Wi-Fi)')
