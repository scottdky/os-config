import logging
from typing import Any, Dict

from lib.operations import OperationBase, OperationLogRecord
from lib.managers.base import BaseManager
from lib.cmdline import loadCmdlineFile, saveCmdlineFile, Cmdline

logger = logging.getLogger(__name__)

class SerialPortOp(OperationBase):
    """
    Configures Hardware UART, Bluetooth sharing, and the Linux kernel console map.

    See `core/serialport.md` for a comprehensive breakdown of the hardware limitations
    (PL011 vs Mini-UART) and the design decisions surrounding Bluetooth mapping.

    NOTE: We intentionally bypass `raspi-config nonint` because it lacks the necessary
    understanding of Pi Bluetooth hardware mapping (dtoverlay=disable-bt / miniuart-bt)
    required to do this safely and idempotently.
    """

    SERIALPORT = 'serialport'

    REQUIRED_CONFIGS = {
        'enable_uart': {
            'type': bool,
            'default': True,
            'prompt': "Enable hardware serial port (TX/RX)? [y/N]: "
        },
        'baudrate': {
            'type': int,
            'default': 115200,
            'prompt': "Baudrate [115200]? "
        },
        'bluetooth': {
            'type': bool,
            'default': False,
            'prompt': "Enable Bluetooth (forces PL011 UART to GPIO if False)? [y/N]: "
        },
        'console': {
            'type': bool,
            'default': False,
            'prompt': "Enable Linux login console over serial port? [y/N]: "
        }
    }

    def __init__(self) -> None:
        super().__init__(self.SERIALPORT, self.SERIALPORT, self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: Dict[str, Any]) -> Dict[str, Any]:
        """Interactively prompt user for missing configs."""
        filledConfigs = {}
        for key in configsToPrompt:
            spec = self.REQUIRED_CONFIGS[key]

            if spec['type'] is bool:
                defaultStr = 'Y' if spec['default'] else 'N'
                valStr = self._prompt_text_value(spec['prompt'], defaultStr).strip().lower()
                if valStr == '':
                    val = spec['default']
                else:
                    val = valStr in ['y', 'yes', 'true', '1']
            else:
                valStr = self._prompt_text_value(spec['prompt'], str(spec['default'])).strip()
                if valStr == '':
                    val = spec['default']
                else:
                    val = int(valStr) if spec['type'] is int else valStr

            filledConfigs[key] = val
        return filledConfigs

    def apply(self, mgr: BaseManager, configs: Dict[str, Any]) -> OperationLogRecord:
        """Apply serial port configuration."""

        # 1. Sanity check: abort if we aren't manipulating a Raspberry Pi environment.
        if not mgr.is_raspi_os():
            return OperationLogRecord(self.SERIALPORT, False, "Skipped","Skipped",
                errors=["Target OS is not Raspberry Pi OS. Serial port hardware config skipped."]
            )

        enableUart = configs.get('enable_uart', True)
        baudrate = configs.get('baudrate', 115200)
        bluetooth = configs.get('bluetooth', False)
        console = configs.get('console', False)

        changed = False

        # 2. Extract cmdline for console modifications
        oldCmdline = loadCmdlineFile(mgr)
        cmds = Cmdline(oldCmdline)

        # 3. Handle Kernel Console binding (cmdline.txt)
        consoleArg = f"console=serial0,{baudrate}"
        if console:
            # Replaces any existing console=serial0 args intelligently
            changed |= cmds.add(consoleArg)
            # systemctl un-mask handles enabling it for live running systems if requested
            _ = mgr.run('systemctl unmask serial-getty@ttyS0.service', sudo=True)
        else:
            changed |= cmds.remove('console=serial0')
            # Blindly shutting it down so the UART is totally quiet on boot
            _ = mgr.run('systemctl mask serial-getty@ttyS0.service', sudo=True)

        if changed:
            saveCmdlineFile(mgr, cmds.contents())
        prevConsoleState = not console if changed else console

        # 4. Handle Hardware Pin and Bluetooth Maps (config.txt)
        configPath = mgr.get_boot_config_path()

        # Hardware Enable
        res = mgr.set_config_line(configPath, 'enable_uart=1', enable=enableUart, sudo=True)
        prevUartState = not enableUart if res else enableUart
        changed |= res

        # Bluetooth Mapping
        if enableUart:
            if bluetooth:
                # Keep bluetooth, push it to secondary mini-UART, reclaim PL011.
                changed |= mgr.set_config_line(configPath, 'dtoverlay=miniuart-bt', enable=True, sudo=True)
                changed |= mgr.set_config_line(configPath, 'dtoverlay=disable-bt', enable=False, sudo=True)
                mgr.run('systemctl enable hciuart', sudo=True)
            else:
                # Default preference: Kill bluetooth, explicitly map PL011 to pins.
                changed |= mgr.set_config_line(configPath, 'dtoverlay=miniuart-bt', enable=False, sudo=True)
                changed |= mgr.set_config_line(configPath, 'dtoverlay=disable-bt', enable=True, sudo=True)
                mgr.run('systemctl disable hciuart', sudo=True)

        # 5. Add default pi user to dialout for access
        userGroups = mgr.run('id pi')
        if userGroups.returnCode == 0 and 'dialout' not in userGroups.stdout:
            mgr.run('usermod -aG dialout pi', sudo=True)
            changed = True

        return OperationLogRecord(self.SERIALPORT, changed,
            previousState=f'UART={prevUartState}, Console={prevConsoleState}',
            currentState=f"UART={enableUart}, BT={bluetooth}, Console={console}",
            errors=[]
        )
