#!/usr/bin/env python3
"""Auto-mount USB Drives on insertion.

Additional info (multi-line): this module follows the operation pipeline
architecture. It configures automatic mounting of USB drives via systemd-mount
safely on read-only systems.

Usage:
    # Standalone - run as script
    python mount_usb.py

    # Programmatic
    from lib.managers import create_manager
    from core.mount_usb import MountUsbOperation

    with create_manager('local') as mgr:
        MountUsbOperation().execute(mgr)
"""

import os
import sys
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
sys.path.append(str(Path(__file__).resolve().parents[1]))  # PROJECT_ROOT
from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline
# pylint: enable=wrong-import-position


class MountUsbOperation(OperationBase):
    """Operation class for configuring automatic mounting of USB drives via systemd-mount safely on read-only systems."""

    def __init__(self) -> None:
        # Define empty requirements since no configuration parameters are currently needed
        requiredConfigs: dict[str, dict[str, Any]] = {}
        super().__init__(moduleName='mount_usb', name='Mount USB Service', requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing configuration values.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.
            allConfigs (dict[str, Any]): Currently resolved configuration.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys (empty for this operation).
        """
        # No configuration items to prompt for
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply the USB mount configuration.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Final resolved config values.

        Returns:
            OperationLogRecord: Result of the USB mount operation execution.
        """
        # Determine the initial state
        packages = ["exfat-fuse", "exfatprogs", "ntfs-3g"]
        packagesInitial = all(mgr.is_pkg_installed(pkg) for pkg in packages)

        baseDir = os.path.dirname(os.path.abspath(__file__))
        localRule = os.path.join(baseDir, 'resources', '99-usb-automount.rules')
        udevRuleDest = '/etc/udev/rules.d/99-usb-automount.rules'

        with open(localRule, 'r', encoding='utf-8') as f:
            localContent = f.read()

        udevRuleInitial = mgr.exists(udevRuleDest) and mgr.read_file(udevRuleDest, sudo=True) == localContent

        previousState = {
            'packagesInstalled': packagesInitial,
            'udevRuleReady': udevRuleInitial
        }

        changed = False
        errors: list[str] = []

        # 1. Install necessary filesystem support packages
        for pkg in packages:
            if mgr.install_pkg(pkg):
                changed = True

        # 2. Deploy the native systemd-mount udev rule
        if not udevRuleInitial:
            try:
                if not mgr.exists(udevRuleDest) or mgr.read_file(udevRuleDest, sudo=True) != localContent:
                    mgr.put(localRule, udevRuleDest, sudo=True)
                    changed = True
            except Exception as e:
                errors.append(f"Failed to deploy udev rule: {e}")

        # Construct the current state description correctly
        currentState = {
            'packagesInstalled': all(mgr.is_pkg_installed(pkg) for pkg in packages),
            'udevRuleReady': mgr.exists(udevRuleDest) and mgr.read_file(udevRuleDest, sudo=True) == localContent
        }

        return OperationLogRecord(
            operationName=self.name,
            changed=changed,
            previousState=previousState,
            currentState=currentState,
            errors=errors
        )


if __name__ == '__main__':
    pipeline = OperationPipeline([MountUsbOperation()])
    pipeline.run_cli('Configure automatic mounting of USB drives.')
