import pytest
from unittest.mock import MagicMock, patch
from core.serialport import HardwareUart, BluetoothMapping, SerialConsole
from lib.managers.base import CommandResult

@pytest.fixture
def mock_mgr():
    mgr = MagicMock()
    mgr.is_raspi_os.return_value = True
    mgr.get_boot_config_path.return_value = '/boot/firmware/config.txt'

    # Mock read_file for config.txt
    mgr.read_file.return_value = "enable_uart=0\ndtoverlay=something"

    # Mock run to simulate systemctl and usermod success
    # 'uid=1000(pi) gid=1000(pi) groups=1000(pi)' means dialout missing
    mgr.run.return_value = CommandResult(
        stdout="uid=1000(pi) gid=1000(pi) groups=1000(pi)",
        stderr="",
        returnCode=0
    )

    return mgr


# --- HardwareUart Tests ---

def test_hardware_uart_skip_non_raspi(mock_mgr):
    mock_mgr.is_raspi_os.return_value = False

    op = HardwareUart()
    compatible, msg = op.is_manager_compatible(mock_mgr)
    assert not compatible
    assert "not Raspberry Pi OS" in msg

def test_hardware_uart_apply(mock_mgr):
    op = HardwareUart()
    configs = {'enable_uart': True}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []
    # read_file returns enable_uart=0, so previous state should be False
    assert record.previousState == "Enabled=False"
    assert record.currentState == "Enabled=True"
    
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'enable_uart=1', enable=True, sudo=True)
    mock_mgr.run.assert_any_call('usermod -aG dialout pi', sudo=True)


# --- BluetoothMapping Tests ---

def test_bluetooth_mapping_disabled_by_default(mock_mgr):
    op = BluetoothMapping()
    configs = {'bluetooth': False}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []
    # read_file mock doesn't have disable-bt, so previous state should be True
    assert record.previousState == "Enabled=True"
    assert record.currentState == "Enabled=False"
    
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=disable-bt', enable=True, sudo=True)
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=miniuart-bt', enable=False, sudo=True)
    mock_mgr.run.assert_any_call('systemctl disable hciuart', sudo=True)


def test_bluetooth_mapping_enabled(mock_mgr):
    # Alter mock to have disable-bt, so previous state is False
    mock_mgr.read_file.return_value = "dtoverlay=disable-bt\nenable_uart=0"
    
    op = BluetoothMapping()
    configs = {'bluetooth': True}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []
    assert record.previousState == "Enabled=False"
    assert record.currentState == "Enabled=True"
    
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=miniuart-bt', enable=True, sudo=True)
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=disable-bt', enable=False, sudo=True)
    mock_mgr.run.assert_any_call('systemctl enable hciuart', sudo=True)


# --- SerialConsole Tests ---

@patch("core.serialport.loadCmdlineFile")
@patch("core.serialport.saveCmdlineFile")
def test_serial_console_apply_enabled(mock_save, mock_load, mock_mgr):
    mock_load.return_value = "console=tty1 root=/dev/mmcblk0p2"
    mock_mgr.mountPath = '/'

    op = SerialConsole()
    configs = {'console': True, 'baudrate': 9600}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []
    # mock_load doesn't have console=serial0, so previous is False, 115200
    assert record.previousState == "Console=False, Baud=115200"
    assert record.currentState == "Console=True, Baud=9600"
    
    mock_save.assert_called_once()
    saved_cmdline = mock_save.call_args[0][1]
    assert "console=serial0,9600" in saved_cmdline

    mock_mgr.run.assert_any_call('systemctl unmask serial-getty@ttyS0.service', sudo=True)
    mock_mgr.run.assert_any_call('systemctl unmask serial-getty@ttyAMA0.service', sudo=True)
    mock_mgr.run.assert_any_call('systemctl enable serial-getty@ttyS0.service', sudo=True)


@patch("core.serialport.loadCmdlineFile")
@patch("core.serialport.saveCmdlineFile")
def test_serial_console_apply_disabled(mock_save, mock_load, mock_mgr):
    mock_load.return_value = "console=serial0,115200 console=tty1 root=/dev/mmcblk0p2"
    mock_mgr.mountPath = '/'

    op = SerialConsole()
    configs = {'console': False, 'baudrate': 115200}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []
    # mock_load has console=serial0,115200, so previous is True, 115200
    assert record.previousState == "Console=True, Baud=115200"
    assert record.currentState == "Console=False, Baud=115200"
    
    mock_save.assert_called_once()
    saved_cmdline = mock_save.call_args[0][1]
    assert "console=serial0" not in saved_cmdline

    mock_mgr.run.assert_any_call('systemctl mask serial-getty@ttyS0.service', sudo=True)
    mock_mgr.run.assert_any_call('systemctl mask serial-getty@ttyAMA0.service', sudo=True)

