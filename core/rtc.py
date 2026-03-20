#!/usr/bin/env python3
"""Setup Real Time Clock (RTC) and Chrony.

Additional info (multi-line): Configures i2c settings and overlays for an RTC
using software i2c, switches the Pi from using Fake HW Clock to the real RTC,
installs chrony, and enables a generic hwclock.service.

Usage:
    # Standalone - run as script
    python core/rtc.py
"""
import sys
import os
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager, get_single_selection
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline, OperationAbortedError
# pylint: enable=wrong-import-position

# pylint: disable=invalid-name, too-many-locals

class RtcOperation(OperationBase):
    """Operation class for setting up an RTC."""

    RTC = 'rtc'
    REQUIRED_CONFIGS = {
        'device': {'type': 'str'}, #, 'default': 'mcp7941x'},
        'addr': {'type': 'str'}, #, 'default': '0x6f'}, # Default I2C address for mcp7941x
        'sdapin': {'type': 'int'}, #, 'default': 22},
        'sclpin': {'type': 'int'}, #, 'default': 23},
    }

    DEVICE_ADDR_MAP = {
        'ds1307': '0x68',
        'ds3231': '0x68',
        'pcf8523': '0x51',
        'mcp7941x': '0x6f',
    }

    def __init__(self) -> None:
        super().__init__(moduleName='rtc', name=self.RTC, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(
        self, mgr: BaseManager, configs_to_prompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing RTC values.

        Args:
            mgr (BaseManager): Active manager instance.
            configs_to_prompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        if not configs_to_prompt:
            return {}

        prompted: dict[str, Any] = {}

        # Handle device selection
        if 'device' in configs_to_prompt:
            options = list(self.DEVICE_ADDR_MAP.keys())
            print("Select RTC Device:")
            selection = get_single_selection(options)
            if selection is None:
                raise OperationAbortedError("User aborted RTC device selection.")
            prompted['device'] = options[selection]

        # Determine I2C address based on selected or default device
        device = prompted.get('device') or allConfigs.get('device')
        defaultAddr = self.DEVICE_ADDR_MAP.get(str(device))

        if 'addr' in configs_to_prompt:
            prompted['addr'] = defaultAddr

        if 'sdapin' in configs_to_prompt:
            val = self._prompt_text_value("Enter SDA pin")
            if not val.strip():
                raise OperationAbortedError("User aborted SDA pin selection.")
            prompted['sdapin'] = int(val) if val.isdigit() else None

        if 'sclpin' in configs_to_prompt:
            val = self._prompt_text_value("Enter SCL pin")
            if not val.strip():
                raise OperationAbortedError("User aborted SCL pin selection.")
            prompted['sclpin'] = int(val) if val.isdigit() else None

        return prompted

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply RTC changes.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Rtc operation record.
        """
        device = configs.get('device')
        addr = configs.get('addr')
        sda = configs.get('sdapin')
        scl = configs.get('sclpin')

        changed = False
        errors: list[str] = []

        print("Setting up RTC...")

        # Install required tools
        pkgResult = mgr.run(
            'DEBIAN_FRONTEND=noninteractive apt-get install -y i2c-tools chrony',
            sudo=True
        )
        if pkgResult.returnCode != 0:
            errors.append(f"Failed to install i2c-tools/chrony: {pkgResult.stderr.strip()}")

        # Enable I2C in boot configuration
        bootConfigPath = mgr.get_boot_file_path('config.txt')
        if mgr.set_config_line(bootConfigPath, 'dtparam=i2c_arm=on', sudo=True):
            changed = True

        # Enable I2C RTC GPIO overlay
        addrStr = f'addr={addr},' if addr else ''
        overlayLine = (
            f'dtoverlay=i2c-rtc-gpio,{device},{addrStr}'
            f'i2c_gpio_sda={sda},i2c_gpio_scl={scl}'
        )
        if mgr.set_config_line(bootConfigPath, overlayLine, sudo=True):
            changed = True

        # Ensure i2c-dev is in /etc/modules
        modulesPath = '/etc/modules'
        modulesContent = mgr.read_file(modulesPath, sudo=True)
        if 'i2c-dev' not in modulesContent:
            mgr.append(modulesPath, 'i2c-dev', sudo=True)
            changed = True

        # Remove fake-hwclock and install hardware clock service
        hwClockService = '/etc/systemd/system/hwclock.service'

        # Ensure fake-hwclock is purged to prevent conflicts
        mgr.run('DEBIAN_FRONTEND=noninteractive apt-get purge -y fake-hwclock', sudo=True)

        if mgr.exists(hwClockService):
            print(f"{hwClockService} already exists.")
        else:
            sourceService = Path(__file__).resolve().parents[1] / 'core' / 'resources' / 'hwclock.service'
            if sourceService.exists():
                mgr.put(str(sourceService), hwClockService, sudo=True)
                changed = True
            else:
                errors.append(f"Missing resource file: {sourceService}")

        # Unmask first, then enable
        unmaskResult = mgr.systemd_unmask('hwclock.service', sudo=True)
        enableResult = mgr.systemd_enable('hwclock.service', hwClockService, 'sysinit.target', sudo=True)

        if not unmaskResult or not enableResult:
            errors.append("Failed to unmask or enable hwclock.service.")

        if not errors:
            changed = True

        currentState = "RTC configured successfully." if not errors else "RTC configuration failed."

        if changed:
            print("...Done setting up RTC")

        return OperationLogRecord(self.RTC, changed, None, currentState, errors)

if __name__ == '__main__':
    run_pipeline = OperationPipeline([RtcOperation()])
    run_pipeline.run_cli('Configure RTC and Chrony')
