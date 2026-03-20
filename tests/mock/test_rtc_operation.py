"""Mock tests for RTC Operation."""
from unittest.mock import MagicMock
import pytest
from core.rtc import RtcOperation
from lib.managers.base import CommandResult

# pylint: disable=redefined-outer-name, protected-access

@pytest.fixture
def mock_mgr():
    """Fixture to provide a mocked Manager."""
    mgr = MagicMock()
    mgr.get_boot_config_path.return_value = '/boot/firmware/config.txt'

    # Assume hw clock service doesn't exist by default
    mgr.exists.return_value = False

    # Assume i2c-dev not in modules
    mgr.read_file.return_value = ""

    # Successful install
    mgr.run.return_value = CommandResult(
        stdout="",
        stderr="",
        returnCode=0
    )

    return mgr


def test_rtc_apply_success(mock_mgr):
    """Test full application of RTC rules successfully."""
    op = RtcOperation()
    configs = {
        'device': 'ds3231',
        'addr': '0x68',
        'sdapin': 22,
        'sclpin': 23
    }

    # Needs to see set_config_line as returning True (changed)
    mock_mgr.set_config_line.return_value = True

    record = op.apply(mock_mgr, configs)

    assert not record.errors
    assert record.changed is True

    # Did it install Chrony?
    mock_mgr.run.assert_any_call(
        'DEBIAN_FRONTEND=noninteractive apt-get install -y i2c-tools chrony',
        sudo=True
    )

    # Did it configure Boot overlays?
    mock_mgr.set_config_line.assert_any_call(
        '/boot/firmware/config.txt', 'dtparam=i2c_arm=on', sudo=True
    )
    mock_mgr.set_config_line.assert_any_call(
        '/boot/firmware/config.txt',
        'dtoverlay=i2c-rtc-gpio,ds3231,addr=0x68,i2c_gpio_sda=22,i2c_gpio_scl=23',
        sudo=True
    )

    # Did it add to modules?
    mock_mgr.append.assert_any_call('/etc/modules', 'i2c-dev', sudo=True)

    # Did it remove fake-hwclock and add hwclock?
    mock_mgr.run.assert_any_call('DEBIAN_FRONTEND=noninteractive apt-get purge -y fake-hwclock', sudo=True)
    mock_mgr.systemd_unmask.assert_called_once_with('hwclock.service', sudo=True)
    mock_mgr.systemd_enable.assert_called_once_with('hwclock.service', '/etc/systemd/system/hwclock.service', 'sysinit.target', sudo=True)

    # Check put method for the service file
    put_args = mock_mgr.put.call_args[0]
    assert put_args[1] == '/etc/systemd/system/hwclock.service'

def test_rtc_apply_already_configured(mock_mgr):
    """Test RTC apply when the service is already present."""
    mock_mgr.exists.return_value = True
    mock_mgr.read_file.return_value = "i2c-dev"
    mock_mgr.set_config_line.return_value = False

    op = RtcOperation()
    configs = {
        'device': 'mcp7941x',
        'addr': None,
        'sdapin': 22,
        'sclpin': 23
    }

    op.apply(mock_mgr, configs)

    # It will not install the clock service again if it exists
    for call in mock_mgr.run.call_args_list:
        assert 'systemctl enable hwclock.service' not in call.args[0]

def test_rtc_prompt_missing(mock_mgr, monkeypatch):
    """Test interactive prompts for missing config keys."""
    op = RtcOperation()

    # Mock the static selection tools and prompt
    monkeypatch.setattr('core.rtc.get_single_selection', lambda x: 2)

    # Monkeypatch the _prompt_text_value method safely
    def fake_prompt(_prompt_text, defaultValue=""):
        if "SDA" in _prompt_text:
            return "22"
        return "23"
    op._prompt_text_value = fake_prompt

    configs_to_prompt = {
        'device': None,
        'addr': None,
        'sdapin': None,
        'sclpin': None
    }

    res = op.prompt_missing_values(mock_mgr, configs_to_prompt, {})

    assert res['device'] == 'pcf8523'
    assert res['addr'] == '0x51' # automatic map lookup
    assert res['sdapin'] == 22
    assert res['sclpin'] == 23

from lib.operations import OperationAbortedError

def test_rtc_prompt_missing_with_valid_device_in_allConfigs(mock_mgr):
    """Test when device is provided correctly in allConfigs, addr is derived."""
    op = RtcOperation()
    configs_to_prompt = {
        'addr': None,
    }
    allConfigs = {
        'device': 'ds3231'
    }
    res = op.prompt_missing_values(mock_mgr, configs_to_prompt, allConfigs)
    assert 'device' not in res
    assert res['addr'] == '0x68'

def test_rtc_prompt_missing_with_invalid_device_in_allConfigs(mock_mgr):
    """Test when an unknown device is in allConfigs, addr is left None."""
    op = RtcOperation()
    configs_to_prompt = {
        'addr': None,
    }
    allConfigs = {
        'device': 'some_invalid_device'
    }
    res = op.prompt_missing_values(mock_mgr, configs_to_prompt, allConfigs)
    
    assert res['addr'] is None

def test_rtc_prompt_aborted_device(mock_mgr, monkeypatch):
    """Test user aborts configuring RTC device."""
    op = RtcOperation()
    monkeypatch.setattr('core.rtc.get_single_selection', lambda x: None)
    configs_to_prompt = {'device': None}
    
    with pytest.raises(OperationAbortedError, match="User aborted RTC device selection."):
        op.prompt_missing_values(mock_mgr, configs_to_prompt, {})

def test_rtc_prompt_aborted_sda(mock_mgr, monkeypatch):
    """Test user aborts configuring SDA pin."""
    op = RtcOperation()
    
    def fake_prompt(_prompt_text, defaultValue=""):
        return ""
    op._prompt_text_value = fake_prompt
    
    configs_to_prompt = {'sdapin': None}
    with pytest.raises(OperationAbortedError, match="User aborted SDA pin selection."):
        op.prompt_missing_values(mock_mgr, configs_to_prompt, {})

def test_rtc_prompt_aborted_scl(mock_mgr, monkeypatch):
    """Test user aborts configuring SCL pin."""
    op = RtcOperation()
    
    def fake_prompt(_prompt_text, defaultValue=""):
        return ""
    op._prompt_text_value = fake_prompt
    
    configs_to_prompt = {'sclpin': None}
    with pytest.raises(OperationAbortedError, match="User aborted SCL pin selection."):
        op.prompt_missing_values(mock_mgr, configs_to_prompt, {})

