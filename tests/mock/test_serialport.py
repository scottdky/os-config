import pytest
from core.serialport import HardwareUart, BluetoothMapping, SerialConsole
from lib.managers.base import CommandResult

# --- HardwareUart Tests ---

def test_hardware_uart_skip_non_raspi(mock_manager):
    mock_manager.is_raspi_os = lambda: False

    op = HardwareUart()
    compatible, msg = op.is_manager_compatible(mock_manager)
    assert not compatible
    assert "not Raspberry Pi OS" in msg

def test_hardware_uart_apply(mock_manager):
    mock_manager.is_raspi_os = lambda: True
    
    mock_manager.write_file('/boot/firmware/config.txt', "enable_uart=0\ndtoverlay=something")

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        if cmd == 'id pi':
            return CommandResult("uid=1000(pi) gid=1000(pi) groups=1000(pi)", "", 0)
        return original_run(cmd, sudo=sudo)
    mock_manager.run = mock_run
    
    op = HardwareUart()

    record = op.apply(mock_manager, {"enable_uart": True})
    assert record.changed is True

    # Check config.txt changed
    config_txt = mock_manager.read_file('/boot/firmware/config.txt')
    assert "enable_uart=1" in config_txt

    # Check user groups modified
    assert any("usermod -aG dialout pi" in cmd for cmd, _ in mock_manager.run_history)

# --- BluetoothMapping Tests ---

def test_bluetooth_mapping_disabled_by_default(mock_manager):
    mock_manager.is_raspi_os = lambda: True
    mock_manager.write_file('/boot/firmware/config.txt', "enable_uart=1\n")
    
    op = BluetoothMapping()
    record = op.apply(mock_manager, {"bluetooth": False})
    
    assert record.changed is True 
    assert "dtoverlay=disable-bt" in mock_manager.read_file('/boot/firmware/config.txt')

def test_bluetooth_mapping_enabled(mock_manager):
    mock_manager.is_raspi_os = lambda: True
    # Start implicitly enabled
    mock_manager.write_file('/boot/firmware/config.txt', "enable_uart=1\n")

    op = BluetoothMapping()
    
    record = op.apply(mock_manager, {"bluetooth": True})

    assert record.changed is True
    assert "dtoverlay=miniuart-bt" in mock_manager.read_file('/boot/firmware/config.txt')

# --- SerialConsole Tests ---

def test_serial_console_apply_enabled(mock_manager):
    mock_manager.is_raspi_os = lambda: True
    mock_manager.write_file('/boot/firmware/cmdline.txt', "console=tty1 root=PARTUUID=1234")

    op = SerialConsole()
    record = op.apply(mock_manager, {"console": True})

    assert record.changed is True

    # Did it add console to cmdline?
    cmdline = mock_manager.read_file('/boot/firmware/cmdline.txt')
    assert "console=serial0,115200" in cmdline

    # Check systemd operations
    assert any("systemctl unmask serial-getty@ttyS0.service" in cmd for cmd, _ in mock_manager.run_history)
    assert any("systemctl enable serial-getty@ttyS0.service" in cmd for cmd, _ in mock_manager.run_history)

def test_serial_console_apply_disabled(mock_manager):
    mock_manager.is_raspi_os = lambda: True
    # Start with it enabled
    mock_manager.write_file('/boot/firmware/cmdline.txt', "console=serial0,115200 console=tty1 root=PARTUUID=1234")

    op = SerialConsole()
    record = op.apply(mock_manager, {"console": False})

    assert record.changed is True

    # Did it remove console from cmdline?
    cmdline = mock_manager.read_file('/boot/firmware/cmdline.txt')
    assert "console=serial0,115200" not in cmdline
    assert "console=tty1" in cmdline

    # Check systemd masking
    assert any("systemctl mask serial-getty@ttyS0.service" in cmd for cmd, _ in mock_manager.run_history)
