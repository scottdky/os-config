import logging
import re
from typing import Any, Dict
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.operations import OperationBase, OperationLogRecord
from lib.managers.base import BaseManager
from lib.cmdline import loadCmdlineFile, saveCmdlineFile, Cmdline

logger = logging.getLogger(__name__)


class HardwareUart(OperationBase):
    """Controls the physical enablement of the serial pins in config.txt."""

    MODULE_NAME = 'serialport'
    NAME = 'hardware_uart'

    REQUIRED_CONFIGS = {
        'enable_uart': {
            'type': bool,
            #'default': True,
            'prompt': "Enable hardware serial port (TX/RX)? [y/N]: "
        }
    }

    def __init__(self) -> None:
        super().__init__(self.MODULE_NAME, self.NAME, self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        return super().is_manager_compatible(mgr)

    def _get_current_state(self, mgr: BaseManager) -> bool:
        """Parse config.txt to determine if UART is currently enabled."""
        config_path = mgr.get_boot_config_path()

        content = mgr.read_file(config_path, sudo=True)
        # Match completely uncommented enable_uart=1 or dtparam=uart0=on
        if re.search(r'^\s*enable_uart\s*=\s*1\s*$', content, re.MULTILINE):
            return True
        if re.search(r'^\s*dtparam\s*=\s*uart0[=]*on\s*$', content, re.MULTILINE):
            return True
        return False

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: Dict[str, Any]) -> Dict[str, Any]:
        filledConfigs = {}
        currState = self._get_current_state(mgr)
        for key in configsToPrompt:
            spec = self.REQUIRED_CONFIGS[key]
            defaultStr = 'Y' if currState else 'N'

            valStr = self._prompt_text_value(spec['prompt'], defaultStr).strip().lower()
            if valStr == '':
                val = currState
            else:
                val = valStr in ['y', 'yes', 'true', '1']

            filledConfigs[key] = val
        return filledConfigs

    def apply(self, mgr: BaseManager, configs: Dict[str, Any]) -> OperationLogRecord:
        enableUart = configs.get('enable_uart', True)
        changed = False
        configPath = mgr.get_boot_config_path()
        prevState = self._get_current_state(mgr)

        # Apply Pin state
        # In newer pi's, dtparam=uart0=on is the preferred method over enable_uart=1
        changed |= mgr.set_config_line(configPath, 'enable_uart=1', enable=enableUart, sudo=True)

        userGroups = mgr.run('id pi')
        if enableUart and userGroups.returnCode == 0 and 'dialout' not in userGroups.stdout:
            mgr.run('usermod -aG dialout pi', sudo=True)
            changed = True

        return OperationLogRecord(self.NAME, changed,
            previousState=f"Enabled={prevState}",
            currentState=f"Enabled={enableUart}"
        )


class BluetoothMapping(OperationBase):
    """Controls the mapping of the PL011 performance UART to GPIO vs Bluetooth."""

    MODULE_NAME = 'serialport'
    NAME = 'bluetooth_mapping'

    REQUIRED_CONFIGS = {
        'bluetooth': {
            'type': bool,
            #'default': False,
            'prompt': "Enable Bluetooth (forces PL011 UART to GPIO if False)? [y/N]: "
        }
    }

    def __init__(self) -> None:
        super().__init__(self.MODULE_NAME, self.NAME, self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        return super().is_manager_compatible(mgr)

    def _get_current_state(self, mgr: BaseManager) -> bool:
        """Parse config.txt to see if disable-bt is explicitly written."""
        config_path = mgr.get_boot_config_path()

        content = mgr.read_file(config_path, sudo=True)
        is_disabled = bool(re.search(r'^\s*dtoverlay\s*=\s*disable-bt\s*$', content, re.MULTILINE))
        return not is_disabled

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: Dict[str, Any]) -> Dict[str, Any]:
        filledConfigs = {}
        currState = self._get_current_state(mgr)
        for key in configsToPrompt:
            spec = self.REQUIRED_CONFIGS[key]
            defaultStr = 'Y' if currState else 'N'

            valStr = self._prompt_text_value(spec['prompt'], defaultStr).strip().lower()
            if valStr == '':
                val = currState
            else:
                val = valStr in ['y', 'yes', 'true', '1']

            filledConfigs[key] = val
        return filledConfigs

    def apply(self, mgr: BaseManager, configs: Dict[str, Any]) -> OperationLogRecord:
        bluetooth = configs.get('bluetooth', False)
        changed = False

        try:
            configPath = mgr.get_boot_config_path()
        except FileNotFoundError as e:
            return OperationLogRecord(self.NAME, changed, "Unknown", "Error", errors=[str(e)])

        prevState = self._get_current_state(mgr)

        if bluetooth:
            changed |= mgr.set_config_line(configPath, 'dtoverlay=miniuart-bt', enable=True, sudo=True)
            changed |= mgr.set_config_line(configPath, 'dtoverlay=disable-bt', enable=False, sudo=True)
            mgr.run('systemctl enable hciuart', sudo=True)
        else:
            changed |= mgr.set_config_line(configPath, 'dtoverlay=miniuart-bt', enable=False, sudo=True)
            changed |= mgr.set_config_line(configPath, 'dtoverlay=disable-bt', enable=True, sudo=True)
            mgr.run('systemctl disable hciuart', sudo=True)

        return OperationLogRecord(self.NAME, changed,
            previousState=f"Enabled={prevState}",
            currentState=f"Enabled={bluetooth}"
        )


class SerialConsole(OperationBase):
    """Configures the Linux serial login shell in cmdline.txt."""

    MODULE_NAME = 'serialport'
    NAME = 'serial_console'

    REQUIRED_CONFIGS = {
        'console': {
            'type': bool,
            #'default': False,
            'prompt': "Enable Linux login console over serial port? [y/N]: "
        },
        'baudrate': {
            'type': int,
            #'default': 115200,
            'prompt': "Baudrate [{default}]: "
        }
    }

    def __init__(self) -> None:
        super().__init__(self.MODULE_NAME, self.NAME, self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        return super().is_manager_compatible(mgr)

    def _get_current_console_state(self, mgr: BaseManager) -> tuple[bool, int]:
        """Check cmdline.txt for existing console= flag and extract baudrate."""
        root_path = getattr(mgr, 'mountPath', '/')
        existing = loadCmdlineFile(root_path)
        cmds = Cmdline(existing)

        args = cmds.find('console=serial0')
        if not args:
            args = cmds.find('console=ttyAMA0') # Alt Pi hardware mapped string

        if args:
            # Expected arg formatting: console=serial0,115200
            val = args[0]
            if ',' in val:
                try:
                    baud = int(val.split(',')[1].strip())
                    return True, baud
                except ValueError:
                    pass
            return True, 115200

        return False, 115200

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: Dict[str, Any]) -> Dict[str, Any]:
        filledConfigs = {}
        currConsole, currBaud = self._get_current_console_state(mgr)

        for key in configsToPrompt:
            spec = self.REQUIRED_CONFIGS[key]

            if key == 'console':
                defaultStr = 'Y' if currConsole else 'N'
                valStr = self._prompt_text_value(spec['prompt'], defaultStr).strip().lower()
                if valStr == '':
                    val = currConsole
                else:
                    val = valStr in ['y', 'yes', 'true', '1']
                filledConfigs[key] = val

            elif key == 'baudrate':
                prompt = spec['prompt'].format(default=currBaud)
                valStr = self._prompt_text_value(prompt, str(currBaud)).strip()
                if valStr == '':
                    val = currBaud
                else:
                    val = int(valStr)
                filledConfigs[key] = val

        return filledConfigs

    def apply(self, mgr: BaseManager, configs: Dict[str, Any]) -> OperationLogRecord:
        console = configs.get('console', False)
        baudrate = configs.get('baudrate', 115200)

        changed = False
        prevConsole, prevBaud = self._get_current_console_state(mgr)

        root_path = getattr(mgr, 'mountPath', '/')
        oldCmdline = loadCmdlineFile(root_path)
        cmds = Cmdline(oldCmdline)

        consoleArg = f"console=serial0,{baudrate}"

        # We want to remove all existing console elements tying up serial hardware
        # before potentially injecting our specific one.
        for existing in cmds.find('console=serial0'):
            cmds.remove(existing)
            changed = True
        for existing in cmds.find('console=ttyAMA0'):
            cmds.remove(existing)
            changed = True

        if console:
            changed |= cmds.add(consoleArg)
            mgr.run('systemctl unmask serial-getty@ttyS0.service', sudo=True)
            mgr.run('systemctl unmask serial-getty@ttyAMA0.service', sudo=True)
            mgr.run('systemctl enable serial-getty@ttyS0.service', sudo=True)
        else:
            mgr.run('systemctl mask serial-getty@ttyS0.service', sudo=True)
            mgr.run('systemctl mask serial-getty@ttyAMA0.service', sudo=True)

        if changed:
            saveCmdlineFile(root_path, cmds.contents())

        return OperationLogRecord(self.NAME, changed,
            previousState=f"Console={prevConsole}, Baud={prevBaud}",
            currentState=f"Console={console}, Baud={baudrate}"
        )


if __name__ == '__main__':
    from lib.operations import OperationPipeline

    pipeline = OperationPipeline([HardwareUart(), BluetoothMapping(), SerialConsole()])
    pipeline.run_cli("Raspberry Pi Serial Port Configuration")
