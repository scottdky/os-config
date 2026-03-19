import pytest
from unittest.mock import MagicMock, patch
from core.serialport import SerialPortOp
from lib.managers.base import CommandResult

@pytest.fixture
def mock_mgr():
    mgr = MagicMock()
    mgr.is_raspi_os.return_value = True
    mgr.get_boot_config_path.return_value = '/boot/firmware/config.txt'

    # Mock run to simulate systemctl and usermod success
    # 'uid=1000(pi) gid=1000(pi) groups=1000(pi)' means dialout missing
    mgr.run.return_value = CommandResult(
        stdout="uid=1000(pi) gid=1000(pi) groups=1000(pi)",
        stderr="",
        returnCode=0
    )

    return mgr

@patch("core.serialport.loadCmdlineFile")
@patch("core.serialport.saveCmdlineFile")
def test_serialport_skip_non_raspi(mock_save, mock_load, mock_mgr):
    mock_mgr.is_raspi_os.return_value = False

    op = SerialPortOp()
    record = op.apply(mock_mgr, {})

    assert record.currentState == "Skipped"
    assert "not Raspberry Pi OS" in record.errors[0]
    mock_mgr.set_config_line.assert_not_called()

@patch("core.serialport.loadCmdlineFile")
@patch("core.serialport.saveCmdlineFile")
def test_serialport_bluetooth_disabled_by_default(mock_save, mock_load, mock_mgr):
    mock_load.return_value = "console=tty1 root=/dev/mmcblk0p2"

    op = SerialPortOp()
    # Configuration with bluetooth=False (disables it to free up PL011)
    configs = {'enable_uart': True, 'bluetooth': False, 'console': False, 'baudrate': 115200}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []

    # Verify hardware UART enabled
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'enable_uart=1', enable=True, sudo=True)

    # Verify bluetooth was disabled and pi pushed to PL011
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=disable-bt', enable=True, sudo=True)
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=miniuart-bt', enable=False, sudo=True)
    # Validate systemd was invoked
    mock_mgr.run.assert_any_call('systemctl disable hciuart', sudo=True)

    # Verify we add pi to dialout since it wasn't in id output
    mock_mgr.run.assert_any_call('usermod -aG dialout pi', sudo=True)

@patch("core.serialport.loadCmdlineFile")
@patch("core.serialport.saveCmdlineFile")
def test_serialport_console_enabled(mock_save, mock_load, mock_mgr):
    mock_load.return_value = "console=tty1 root=/dev/mmcblk0p2"

    op = SerialPortOp()
    # Configuration to turn on console
    configs = {'enable_uart': True, 'bluetooth': True, 'console': True, 'baudrate': 9600}
    record = op.apply(mock_mgr, configs)

    assert record.errors == []

    # cmdline should be updated with the console argument
    mock_save.assert_called_once()
    saved_cmdline = mock_save.call_args[0][1]
    assert "console=serial0,9600" in saved_cmdline

    mock_mgr.run.assert_any_call('systemctl unmask serial-getty@ttyS0.service', sudo=True)

    # Since BT is True, we keep it but assign to miniuart
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=miniuart-bt', enable=True, sudo=True)
    mock_mgr.set_config_line.assert_any_call('/boot/firmware/config.txt', 'dtoverlay=disable-bt', enable=False, sudo=True)
    mock_mgr.run.assert_any_call('systemctl enable hciuart', sudo=True)
