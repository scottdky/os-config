#!/usr/bin/env python3
"""Setup Wayland Kiosk Mode.

Configures Raspberry Pi OS to boot into a Wayland-based Kiosk mode using
Cage and Chromium. It sets up the required packages, installs a transparent
cursor theme to hide the mouse, and configures the startup systemd services
for the kiosk and the corresponding local webserver.
"""
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class KioskOperation(OperationBase):
    """Operation class for setting up Wayland kiosk mode."""

    KIOSK = 'kiosk'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='kiosk', name=self.KIOSK, requiredConfigs=self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_os_image():
            return False, "Target must be a mounted OS image."
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        return super().is_manager_compatible(mgr)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt user for missing configuration values."""
        return {}

    def _install_packages(self, mgr: BaseManager) -> bool:
        """Installs the necessary Wayland, Chromium, and Kiosk dependency packages."""
        changed = False

        # We also fetch git, screen, etc from the old requirements just in case
        packages = [
            'cage',
            'chromium-browser',
            'xcursor-transparent-theme',
            'git',
            'screen',
            'libavahi-compat-libdnssd1',
            'python3-pip',
            'python3-dev'
        ]

        for pkg in packages:
            changed |= mgr.install_pkg(pkg)

        # Optional: uninstall unused x11 stuff if it's there
        changed |= mgr.remove_pkg('xserver-xorg', purge=True)
        changed |= mgr.remove_pkg('xinit', purge=True)

        return changed

    def _setup_services(self, mgr: BaseManager) -> bool:
        """Sets up the kiosk and webserver systemd services."""
        changed = False

        # Paths
        base_path = Path(__file__).resolve().parent
        kiosk_service_src = base_path / 'resources' / 'kiosk.service'
        kiosk_service_tgt = '/etc/systemd/system/kiosk.service'

        webserver_service_src = base_path / 'resources' / 'webserver.service'
        webserver_service_tgt = '/etc/systemd/system/webserver.service'

        # Kiosk Service
        kiosk_content_local = kiosk_service_src.read_text(encoding='utf-8')
        kiosk_content_remote = mgr.read_file(kiosk_service_tgt, sudo=True)

        if kiosk_content_local != kiosk_content_remote:
            mgr.put(str(kiosk_service_src), kiosk_service_tgt, sudo=True)
            mgr.systemd_enable('kiosk.service', servicePath=kiosk_service_tgt, sudo=True)
            changed = True

        # Webserver Service
        webserver_content_local = webserver_service_src.read_text(encoding='utf-8')
        webserver_content_remote = mgr.read_file(webserver_service_tgt, sudo=True)

        if webserver_content_local != webserver_content_remote:
            mgr.put(str(webserver_service_src), webserver_service_tgt, sudo=True)
            mgr.systemd_enable('webserver.service', servicePath=webserver_service_tgt, sudo=True)
            changed = True

        return changed

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply Kiosk configuration.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Result record.
        """
        changed = False
        errors: list[str] = []

        print("Setting up Wayland Kiosk environment...")

        try:
            changed |= self._install_packages(mgr)
            changed |= self._setup_services(mgr)
        except Exception as e:
            errors.append(f"Failed configuring Kiosk: {str(e)}")

        currentState = "System staged for Wayland Kiosk mode." if not errors else "Kiosk configuration failed."

        if changed:
            print("...Done configuring Kiosk.")

        return OperationLogRecord(self.KIOSK, changed, None, currentState, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([KioskOperation()])
    pipeline.run_cli('Configure Wayland Kiosk Mode')
