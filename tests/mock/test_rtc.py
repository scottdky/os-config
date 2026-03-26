import pytest
from core.rtc import RtcOperation
from lib.managers.base import CommandResult
from lib.operations import OperationAbortedError

def test_rtc_apply_success(mock_manager):
    """Test full application of RTC rules successfully."""
    op = RtcOperation()
    configs = {
        'device': 'ds3231',
        'addr': '0x68',
        'sdapin': 22,
        'sclpin': 23
    }
    
    # Pre-setup system files
    mock_manager.write_file('/boot/firmware/config.txt', '')
    mock_manager.write_file('/etc/modules', '')

    record = op.apply(mock_manager, configs)

    assert not record.errors
    assert record.changed is True

    # Check that apt-get ran
    assert any("apt-get install -y i2c-tools chrony" in cmd for cmd, _ in mock_manager.run_history)
    # Check new config state
    config_txt = mock_manager.read_file('/boot/firmware/config.txt')
    assert 'dtparam=i2c_arm=on' in config_txt
    assert 'dtoverlay=i2c-rtc-gpio,ds3231,addr=0x68,i2c_gpio_sda=22,i2c_gpio_scl=23' in config_txt
    # Check modules setup
    modules_txt = mock_manager.read_file('/etc/modules')
    assert 'i2c-dev' in modules_txt
    
    # Check services run/install
    assert any("apt-get purge -y fake-hwclock" in cmd for cmd, _ in mock_manager.run_history)

def test_rtc_apply_already_configured(mock_manager):
    """Test RTC apply when it's already mostly configured. Note that RTC currently always runs apt-get and reports changed=True."""
    op = RtcOperation()
    configs = {
        'device': 'mcp7941x',
        'addr': '',
        'sdapin': 22,
        'sclpin': 23
    }

    mock_manager.write_file('/boot/firmware/config.txt', 
                            'dtparam=i2c_arm=on\ndtoverlay=i2c-rtc-gpio,mcp7941x,i2c_gpio_sda=22,i2c_gpio_scl=23\n')
    mock_manager.write_file('/etc/modules', 'i2c-dev\n')
    mock_manager.write_file('/etc/systemd/system/hwclock.service', 'dummy data')

    record = op.apply(mock_manager, configs)
    
    # Due to unconditional changed=True in rtc.py
    assert record.changed is True
    assert record.errors == []

def test_rtc_prompt_missing(mock_manager, monkeypatch):
    """Test interactive prompts for missing config keys."""
    op = RtcOperation()

    monkeypatch.setattr('core.rtc.get_single_selection', lambda x: 2)

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

    res = op.prompt_missing_values(mock_manager, configs_to_prompt, {})

    assert res['device'] == 'pcf8523'
    assert res['addr'] == '0x51' # automatic map lookup
    assert res['sdapin'] == 22
    assert res['sclpin'] == 23


def test_rtc_prompt_missing_with_valid_device_in_allConfigs(mock_manager):
    """Test when device is provided correctly in allConfigs, addr is derived."""
    op = RtcOperation()
    configs_to_prompt = {
        'addr': None,
    }
    allConfigs = {
        'device': 'ds3231'
    }
    res = op.prompt_missing_values(mock_manager, configs_to_prompt, allConfigs)
    assert 'device' not in res
    assert res['addr'] == '0x68'

def test_rtc_prompt_missing_with_invalid_device_in_allConfigs(mock_manager):
    """Test when an unknown device is in allConfigs, addr is left None."""
    op = RtcOperation()
    configs_to_prompt = {
        'addr': None,
    }
    allConfigs = {
        'device': 'some_invalid_device'
    }
    res = op.prompt_missing_values(mock_manager, configs_to_prompt, allConfigs)
    
    assert res['addr'] is None

def test_rtc_prompt_aborted_device(mock_manager, monkeypatch):
    """Test user aborts configuring RTC device."""
    op = RtcOperation()
    monkeypatch.setattr('core.rtc.get_single_selection', lambda x: None)
    configs_to_prompt = {'device': None}

    with pytest.raises(OperationAbortedError, match="User aborted RTC device selection."):
        op.prompt_missing_values(mock_manager, configs_to_prompt, {})

def test_rtc_prompt_aborted_sda(mock_manager, monkeypatch):
    """Test user aborts configuring SDA pin."""
    op = RtcOperation()
    def fake_prompt(_prompt_text, defaultValue=""):
        return ""
    op._prompt_text_value = fake_prompt
    configs_to_prompt = {'sdapin': None}
    with pytest.raises(OperationAbortedError, match="User aborted SDA pin selection."):
        op.prompt_missing_values(mock_manager, configs_to_prompt, {})

def test_rtc_prompt_aborted_scl(mock_manager, monkeypatch):
    """Test user aborts configuring SCL pin."""
    op = RtcOperation()
    def fake_prompt(_prompt_text, defaultValue=""):
        return ""
    op._prompt_text_value = fake_prompt
    configs_to_prompt = {'sclpin': None}
    with pytest.raises(OperationAbortedError, match="User aborted SCL pin selection."):
        op.prompt_missing_values(mock_manager, configs_to_prompt, {})
