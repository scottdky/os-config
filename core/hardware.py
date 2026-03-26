#!/usr/bin/env python3
"""Manage hardware configuration for embedded devices.

Allows configuration of SPI, I2C, Power Toggle (GPIO), and custom variables,
skipping interactive prompting.

Usage: Configure 'hardware' root in config.yaml.
"""
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class SpiOperation(OperationBase):
    SPI = 'spi'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='hardware', name=self.SPI, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        enable = configs.get(self.SPI, False)

        if not isinstance(enable, bool) or not enable:
            return OperationLogRecord(self.SPI, False, None, "Spi skip", [])

        boot_file = mgr.get_boot_file_path('config.txt')
        res = mgr.set_config_line(boot_file, 'dtparam=spi=on', sudo=True)

        return OperationLogRecord(self.SPI, res, None, "Enabled SPI", [])


class I2cOperation(OperationBase):
    I2C = 'i2c'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='hardware', name=self.I2C, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        enable = configs.get(self.I2C, False)

        if not isinstance(enable, bool) or not enable:
            return OperationLogRecord(self.I2C, False, None, "I2C skip", [])

        boot_file = mgr.get_boot_file_path('config.txt')
        res = mgr.set_config_line(boot_file, 'dtparam=i2c_arm=on', sudo=True)

        return OperationLogRecord(self.I2C, res, None, "Enabled I2C", [])


class PowerToggleOperation(OperationBase):
    POWER = 'power_toggle'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='hardware', name=self.POWER, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        enable = configs.get(self.POWER, False)

        if not isinstance(enable, bool) or not enable:
            return OperationLogRecord(self.POWER, False, None, "Power Toggle skip", [])

        boot_file = mgr.get_boot_file_path('config.txt')
        res1 = mgr.set_config_line(boot_file, 'dtoverlay=gpio-shutdown', sudo=True)
        res2 = mgr.set_config_line(boot_file, 'dtoverlay=i2c1,pins_44_45', sudo=True)

        changed = res1 or res2
        return OperationLogRecord(self.POWER, changed, None, "Enabled Power Toggle (GPIO shutdown + inline I2C overlay)", [])


class UdevOperation(OperationBase):
    UDEV = 'udev'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='hardware', name=self.UDEV, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        changed = False
        errors: list[str] = []
        udev_configs = configs.get(self.UDEV, {})

        if not udev_configs:
            return OperationLogRecord(self.UDEV, False, None, "No udev rules configured", [])

        if not isinstance(udev_configs, dict):
            errors.append(f"Invalid udev format. Expected mapping of filename to rules, got {type(udev_configs).__name__}")
            return OperationLogRecord(self.UDEV, False, None, "Failed", errors)

        for filename, rules in udev_configs.items():
            if not filename.endswith('.rules'):
                filename += '.rules'

            target = f"/etc/udev/rules.d/{filename}"
            orig_content = mgr.read_file(target, sudo=True) if mgr.exists(target) else None

            if orig_content != rules:
                mgr.write_file(target, rules, sudo=True)
                changed = True

        if changed:
            mgr.run("udevadm control --reload-rules", sudo=True)
            mgr.run("udevadm trigger", sudo=True)

        state = f"Provisioned {len(udev_configs)} udev rule files."
        if errors:
            state = "Completed with errors."

        return OperationLogRecord(self.UDEV, changed, None, state, errors)


class CustomConfigOperation(OperationBase):
    CUSTOM = 'custom_config'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='hardware', name=self.CUSTOM, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        changed = False
        errors: list[str] = []
        lines = configs.get(self.CUSTOM, [])

        if not lines:
            return OperationLogRecord(self.CUSTOM, False, None, "No custom boot configs specified", [])

        if not isinstance(lines, list):
            errors.append(f"Invalid custom_config format. Expected list, got {type(lines).__name__}")
            return OperationLogRecord(self.CUSTOM, False, None, "Failed", errors)

        boot_file = mgr.get_boot_file_path('config.txt')
        for line in lines:
            try:
                res = mgr.set_config_line(boot_file, str(line), sudo=True)
                if res:
                    changed = True
            except Exception as e:
                errors.append(f"Failed to set config line '{line}': {e}")

        state = f"Applied {len(lines)} custom boot parameters."
        if errors:
            state += f" ({len(errors)} errors)"

        return OperationLogRecord(self.CUSTOM, changed, None, state, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([
        SpiOperation(),
        I2cOperation(),
        PowerToggleOperation(),
        UdevOperation(),
        CustomConfigOperation()
    ])
    pipeline.run_cli('Set Hardware Configs')
