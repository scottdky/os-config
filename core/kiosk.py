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
    REQUIRED_CONFIGS = {
        'loading_style': {
            'type': 'str',
            'prompt': 'Select loading screen style'
        }
    }

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
        results = {}

        if 'loading_style' in configsToPrompt:
            choices = ['black', 'spinner', 'text']
            sel = self.prompt_menu_value(self.REQUIRED_CONFIGS['loading_style']['prompt'], choices, 'spinner')

            style = choices[sel] if sel >= 0 else 'spinner'
            results['loading_style'] = style

            if style == 'text' and 'loading_text' not in allConfigs:
                prompt = "Enter text for the loading screen [{default}]: "
                ans = self._prompt_text_value(prompt, "System Starting...").strip()
                results['loading_text'] = ans if ans else "System Starting..."

        return results

    def _install_packages(self, mgr: BaseManager) -> bool:
        """Installs the necessary Wayland, Chromium, and Kiosk dependency packages."""
        changed = False

        # We also fetch git, screen, etc from the old requirements just in case
        packages = [
            'cage',
            'chromium-browser',
            'xcursor-transparent-theme',
            'git',
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

    def _setup_services(self, mgr: BaseManager, configs: dict[str, Any]) -> bool:
        """Sets up the kiosk display and loading page."""
        changed = False

        # Create scripts directory for pi user
        target_scripts_dir = "/home/pi/bin/scripts"
        mgr.run(f"mkdir -p {target_scripts_dir}", sudo=True)
        mgr.run("chown -R pi:pi /home/pi/bin", sudo=True)

        # Paths
        base_path = Path(__file__).resolve().parent
        kiosk_service_src = base_path / 'resources' / 'kiosk.service'
        kiosk_service_tgt = '/etc/systemd/system/kiosk.service'

        startkiosk_script_src = base_path / 'resources' / 'startkiosk.sh'
        startkiosk_script_tgt = f'{target_scripts_dir}/startkiosk.sh'

        # Kiosk Script provision
        kiosk_script_local = startkiosk_script_src.read_text(encoding='utf-8')
        kiosk_script_remote = mgr.read_file(startkiosk_script_tgt, sudo=True)
        if kiosk_script_local != kiosk_script_remote:
            mgr.put(str(startkiosk_script_src), startkiosk_script_tgt, sudo=True)
            mgr.run(f'chmod +x {startkiosk_script_tgt}', sudo=True)
            mgr.run(f'chown pi:pi {startkiosk_script_tgt}', sudo=True)
            changed = True

        # Loading HTML
        style = configs.get('loading_style', 'spinner')
        html_src = base_path / 'resources' / f'loading_{style}.html'
        html_content = html_src.read_text(encoding='utf-8')
        if style == 'text':
            loading_text = configs.get('loading_text', 'System Starting...')
            html_content = html_content.replace('{{LOADING_TEXT}}', loading_text)

        target_html = f'{target_scripts_dir}/loading.html'
        html_remote = mgr.read_file(target_html, sudo=True)
        if html_content != html_remote:
            mgr.write_file(target_html, html_content, sudo=True)
            mgr.run(f'chown pi:pi {target_html}', sudo=True)
            changed = True

        # Kiosk Service
        kiosk_content_local = kiosk_service_src.read_text(encoding='utf-8')
        kiosk_content_remote = mgr.read_file(kiosk_service_tgt, sudo=True)

        if kiosk_content_local != kiosk_content_remote:
            mgr.put(str(kiosk_service_src), kiosk_service_tgt, sudo=True)
            mgr.systemd_enable('kiosk.service', servicePath=kiosk_service_tgt, sudo=True)
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
            changed |= self._setup_services(mgr, configs)
        except Exception as e:
            errors.append(f"Failed configuring Kiosk: {str(e)}")

        currentState = "System staged for Wayland Kiosk mode." if not errors else "Kiosk configuration failed."

        if changed:
            print("...Done configuring Kiosk.")

        return OperationLogRecord(self.KIOSK, changed, None, currentState, errors)


class ScreenDimmerOperation(OperationBase):
    """Operation class for installing and staging the Wayland screen dimmer."""

    SCREEN_DIMMER = 'screendimmer'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='kiosk', name=self.SCREEN_DIMMER, requiredConfigs=self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        if not mgr.is_os_image():
            return False, "Target must be a mounted OS image."
        return super().is_manager_compatible(mgr)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt user for missing configuration values."""
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply the screen dimmer script changes.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Operation record.
        """
        changed = False
        errors: list[str] = []

        print("Setting up Screen Dimmer environment...")

        try:
            # Install necessary packages for Wayland idle/backlight management
            for pkg in ['swayidle', 'brightnessctl']:
                changed |= mgr.install_pkg(pkg)

            # Ensure 'pi' user has permissions to modify backlight via brightnessctl
            # (which uses systemd/udev rules that allow users in 'video' group to change it natively)
            if mgr.run('sudo usermod -aG video pi').returnCode == 0:
                changed = True

            # Stage the dimmer script
            targetScriptsDir = "/home/pi/bin/scripts"
            targetScript = f"{targetScriptsDir}/startdimmer.sh"

            mgr.run(f"mkdir -p {targetScriptsDir}", sudo=True)
            mgr.run("chown -R pi:pi /home/pi/bin", sudo=True)

            srcScript = Path(__file__).resolve().parent / 'resources' / 'startdimmer.sh'
            script_local = srcScript.read_text(encoding='utf-8')
            script_remote = mgr.read_file(targetScript, sudo=True)

            if script_local != script_remote:
                mgr.put(str(srcScript), targetScript, sudo=True)
                mgr.run(f"chmod +x {targetScript}", sudo=True)
                mgr.run(f"chown pi:pi {targetScript}", sudo=True)
                changed = True

        except Exception as e:
            errors.append(f"Failed configuring screen dimmer: {str(e)}")

        currentState = "System staged for Wayland idle screen dimming." if not errors else "Screen dimmer configuration failed."

        if changed:
            print("...Done configuring screen dimmer.")

        return OperationLogRecord(self.SCREEN_DIMMER, changed, None, currentState, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([KioskOperation(), ScreenDimmerOperation()])
    pipeline.run_cli('Configure Wayland Kiosk Mode and Screen Dimmer')
