#!/usr/bin/env python3
"""Manage generic package installations.

Allows automated installation of apt and pip packages driven exactly by the user's
config.yaml, completely skipping interactive prompting.

Usage: Configure 'packages' root in config.yaml.
"""
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class AptPackagesOperation(OperationBase):
    """Operation class for installing apt packages from config."""

    APT = 'apt'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='packages', name=self.APT, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        changed = False
        errors: list[str] = []
        pkgs = configs.get(self.APT, [])

        if not pkgs:
            return OperationLogRecord(self.APT, False, None, "No apt packages specified in config", [])

        if not isinstance(pkgs, list):
            errors.append(f"Invalid package list format. Expected array, got {type(pkgs).__name__}")
            return OperationLogRecord(self.APT, False, None, "Failed", errors)

        installed_list = []
        for pkg in pkgs:
            try:
                # BaseManager.install_pkg returns True if it modified the system
                if mgr.install_pkg(str(pkg)):
                    changed = True
                    installed_list.append(str(pkg))
            except Exception as e:
                errors.append(f"Failed installing {pkg}: {str(e)}")

        state = f"Installed {len(installed_list)} apt packages." if installed_list else "All requested apt packages already present."
        if errors:
            state = "Completed with errors."

        return OperationLogRecord(self.APT, changed, None, state, errors)


class PipPackagesOperation(OperationBase):
    """Operation class for installing pip packages from config."""

    PIP = 'pip'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='packages', name=self.PIP, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        changed = False
        errors: list[str] = []
        pkgs = configs.get(self.PIP, [])

        if not pkgs:
            return OperationLogRecord(self.PIP, False, None, "No pip packages specified in config", [])

        if not isinstance(pkgs, list):
            errors.append(f"Invalid package list format. Expected array, got {type(pkgs).__name__}")
            return OperationLogRecord(self.PIP, False, None, "Failed", errors)

        installed_list = []
        for pkg in pkgs:
            try:
                # We install system-wide intentionally for Kiosk/Embedded OS images.
                # If managed-environment barriers (--break-system-packages) are active in newer RaspiOS,
                # they will need to be explicitly bypassed here.
                res = mgr.run(f"pip3 install {pkg} --break-system-packages", sudo=True)
                if res.returnCode != 0:
                    errors.append(f"Failed installing pip pkg {pkg}: {res.stderr}")
                else:
                    changed = True
                    installed_list.append(str(pkg))
            except Exception as e:
                errors.append(f"Error installing {pkg}: {str(e)}")

        state = f"Attempted install for {len(installed_list)} pip packages." if installed_list else "Pip operation completed."
        if errors:
            state = "Completed with errors."

        return OperationLogRecord(self.PIP, changed, None, state, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([AptPackagesOperation(), PipPackagesOperation()])
    pipeline.run_cli('Install generic software packages via Apt/Pip')
