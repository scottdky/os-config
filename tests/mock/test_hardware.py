import pytest
from core.hardware import (
    SpiOperation,
    I2cOperation,
    PowerToggleOperation,
    UdevOperation,
    CustomConfigOperation
)

def setup_boot_file(mock_manager):
    # BaseManager expects /boot/firmware/config.txt or /boot/config.txt
    mock_manager.write_file('/boot/firmware/config.txt', '# Initial config\n')

def test_spi_operation(mock_manager):
    setup_boot_file(mock_manager)
    op = SpiOperation()

    # Test True
    record = op.apply(mock_manager, {"spi": True})
    assert record.changed is True
    content = mock_manager.read_file("/boot/firmware/config.txt")
    assert "dtparam=spi=on" in content

    # Test Idempotency
    record = op.apply(mock_manager, {"spi": True})
    assert record.changed is False

    # Test False
    record = op.apply(mock_manager, {"spi": False})
    assert record.changed is False

def test_i2c_operation(mock_manager):
    setup_boot_file(mock_manager)
    op = I2cOperation()

    # Test True
    record = op.apply(mock_manager, {"i2c": True})
    assert record.changed is True
    content = mock_manager.read_file("/boot/firmware/config.txt")
    assert "dtparam=i2c_arm=on" in content

    # Test Idempotency
    record = op.apply(mock_manager, {"i2c": True})
    assert record.changed is False

def test_power_toggle_operation(mock_manager):
    setup_boot_file(mock_manager)
    op = PowerToggleOperation()

    record = op.apply(mock_manager, {"power_toggle": True})
    assert record.changed is True
    content = mock_manager.read_file("/boot/firmware/config.txt")
    assert "dtoverlay=gpio-shutdown" in content
    assert "dtoverlay=i2c1,pins_44_45" in content

    record = op.apply(mock_manager, {"power_toggle": True})
    assert record.changed is False

def test_udev_operation(mock_manager):
    op = UdevOperation()
    configs = {
        "udev": {
            "99-test": "ACTION==\"add\", SUBSYSTEM==\"input\", RUN+=\"/bin/test\"\n"
        }
    }

    record = op.apply(mock_manager, configs)
    assert record.changed is True
    assert mock_manager.read_file("/etc/udev/rules.d/99-test.rules") == "ACTION==\"add\", SUBSYSTEM==\"input\", RUN+=\"/bin/test\"\n"

    # Expect udevadm reload
    reload_run = any(cmd for cmd, _ in mock_manager.run_history if "udevadm control --reload-rules" in cmd)
    assert reload_run

    # Idempotency
    record = op.apply(mock_manager, configs)
    assert record.changed is False

def test_custom_config_operation(mock_manager):
    setup_boot_file(mock_manager)
    op = CustomConfigOperation()

    configs = {
        "custom_config": ["gpu_mem=128", "enable_uart=1"]
    }

    record = op.apply(mock_manager, configs)
    assert record.changed is True
    content = mock_manager.read_file("/boot/firmware/config.txt")
    assert "gpu_mem=128" in content
    assert "enable_uart=1" in content

    record = op.apply(mock_manager, configs)
    assert record.changed is False
