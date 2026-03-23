#!/usr/bin/env python3
"""Set custom boot splash screen using Plymouth.

Additional info (multi-line): configures a modern RaspiOS system to display a
custom image during boot using Plymouth. Disables default kernel logging and
rainbow splash. Suppresses console graphics.

Usage:
    # Standalone - run as script
    python core/splashscreen.py     # Interactive operation, will prompt for image path

    # Programmatic
    from lib.managers import create_manager
    from core.splashscreen import SplashscreenOperation

    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        SplashscreenOperation().execute(mgr)

Configuration:
    Add to config.yaml:
    splashscreen:
        image_path: /path/to/local/splash.png   # Optional. If missing, will prompt.
"""
import os
import sys
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationAbortedError, OperationPipeline
from lib.cmdline import Cmdline, loadCmdlineFile, saveCmdlineFile
# pylint: enable=wrong-import-position


class SplashscreenOperation(OperationBase):
    """Operation class for setting a custom Plymouth splash screen."""

    SPLASHSCREEN = 'splashscreen'
    IMAGE_PATH = 'image_path'
    REQUIRED_CONFIGS = {
        'type': 'str',
        'prompt': 'Enter path to the splashscreen image (press Enter to keep default: {default})',
    }

    THEME_NAME = 'custom-splash'
    THEME_DIR = f'/usr/share/plymouth/themes/{THEME_NAME}'
    TARGET_IMAGE_NAME = 'splash.png'
    TARGET_IMAGE_PATH = f'{THEME_DIR}/{TARGET_IMAGE_NAME}'

    # Legacy image path from older version is checked in case we can reuse it
    LEGACY_IMAGE_PATH = '/opt/splash.png'

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.IMAGE_PATH: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='splashscreen', name=self.SPLASHSCREEN, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for missing image_path config value.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.
            allConfigs (dict[str, Any]): All currently resolved configs.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.

        Raises:
            OperationAbortedError: If no image path is provided or if the provided path is invalid.
        """
        if self.IMAGE_PATH not in configsToPrompt:
            return {}

        currImage = ''
        if mgr.exists(self.TARGET_IMAGE_PATH):
            currImage = self.TARGET_IMAGE_PATH
        elif mgr.exists(self.LEGACY_IMAGE_PATH):
            currImage = self.LEGACY_IMAGE_PATH

        prompt = self.REQUIRED_CONFIGS['prompt']
        if not currImage:
            prompt = prompt.replace(' (press Enter to keep default: {default})', '')

        imagePath = self._prompt_text_value(prompt, currImage).strip()
        if not imagePath:
            imagePath = currImage

        if not imagePath:
            raise OperationAbortedError("No image path provided and no existing image found on target system.")

        if imagePath not in (self.TARGET_IMAGE_PATH, self.LEGACY_IMAGE_PATH) and not os.path.isfile(imagePath):
            raise OperationAbortedError(f"Provided path is not a valid local file: {imagePath}")

        return {self.IMAGE_PATH: imagePath}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply splash screen changes.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values containing image_path.

        Returns:
            OperationLogRecord: Splashscreen operation record.
        """
        imagePathStr = str(configs.get(self.IMAGE_PATH, ''))

        # 1. Update config.txt to disable rainbow color splash
        configPath = mgr.get_boot_file_path('config.txt')
        mgr.append(configPath, 'disable_splash=1', sudo=True)

        # 2. Update cmdline.txt for modern splash options
        originalCmdlineStr = loadCmdlineFile(mgr)
        cmdline = Cmdline(originalCmdlineStr)

        flagsToAdd = [
            'quiet',
            'splash',
            'plymouth.ignore-serial-consoles',
            'logo.nologo',
            'consoleblank=0',
            'loglevel=1',
            'vt.global_cursor_default=0'
        ]

        for flag in flagsToAdd:
            cmdline.add(flag)

        newCmdlineStr = cmdline.contents()
        if newCmdlineStr != originalCmdlineStr:
            saveCmdlineFile(mgr, newCmdlineStr)

        # 3. Create theme directory and transfer/setup the image
        mgr.run(f'mkdir -p {self.THEME_DIR}', sudo=True)

        if imagePathStr and imagePathStr not in (self.TARGET_IMAGE_PATH, self.LEGACY_IMAGE_PATH):
            mgr.put(imagePathStr, self.TARGET_IMAGE_PATH, sudo=True)
        elif imagePathStr == self.LEGACY_IMAGE_PATH and not mgr.exists(self.TARGET_IMAGE_PATH):
            mgr.run(f'cp {self.LEGACY_IMAGE_PATH} {self.TARGET_IMAGE_PATH}', sudo=True)

        # 4. Create Plymouth theme files
        plymouthConf = f"""[Plymouth Theme]
Name=Custom Splash
Description=A minimal single-image splash screen
ModuleName=script

[script]
ImageDir={self.THEME_DIR}
ScriptFile={self.THEME_DIR}/{self.THEME_NAME}.script
"""
        mgr.write_file(f"{self.THEME_DIR}/{self.THEME_NAME}.plymouth", plymouthConf, sudo=True)

        plymouthScript = f"""Window.SetBackgroundTopColor(0.0, 0.0, 0.0);
Window.SetBackgroundBottomColor(0.0, 0.0, 0.0);

splash_image = Image("{self.TARGET_IMAGE_NAME}");
splash_sprite = Sprite(splash_image);

splash_sprite.SetX(Window.GetWidth() / 2 - splash_image.GetWidth() / 2);
splash_sprite.SetY(Window.GetHeight() / 2 - splash_image.GetHeight() / 2);
"""
        mgr.write_file(f"{self.THEME_DIR}/{self.THEME_NAME}.script", plymouthScript, sudo=True)

        # 5. Install first-boot service to reliably run apt-get and update-initramfs on hardware
        print("Staging first-boot service to register Plymouth...")
        srcScript = Path(__file__).resolve().parent / 'resources' / 'splashscreen_install.sh'
        srcService = Path(__file__).resolve().parent / 'resources' / 'splashscreen_install.service'

        tgtScript = '/usr/local/bin/splashscreen_install.sh'
        tgtService = '/etc/systemd/system/splashscreen_install.service'

        mgr.put(str(srcScript), tgtScript, sudo=True)
        mgr.run(f'chmod +x {tgtScript}', sudo=True)

        mgr.put(str(srcService), tgtService, sudo=True)
        mgr.systemd_enable('splashscreen_install.service', servicePath=tgtService, sudo=True)

        return OperationLogRecord(self.name, changed=True, previousState=originalCmdlineStr, currentState="Staged Plymouth configuration for first-boot")


if __name__ == '__main__':
    pipeline = OperationPipeline([SplashscreenOperation()])
    pipeline.run_cli('Configure custom splashscreen')
