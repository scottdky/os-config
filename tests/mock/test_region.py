import pytest
import os
from pathlib import Path
from core.region import TimezoneOperation, LocaleOperation
from lib.managers.base import CommandResult

def test_timezone_operation_image(mock_manager, monkeypatch):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    # Needs a /usr/share/zoneinfo/US/Pacific file to pretend it's valid
    Path(mock_manager._resolve_path('usr/share/zoneinfo/US')).mkdir(parents=True, exist_ok=True)
    mock_manager.write_file('/usr/share/zoneinfo/US/Pacific', 'tzdata')
    mock_manager.write_file('/etc/timezone', 'US/Eastern\n')

    tz_state = {'tz': 'US/Eastern'}
    def mock_get_current_timezone(mgr):
        return tz_state['tz']
    monkeypatch.setattr(TimezoneOperation, 'get_current_timezone', mock_get_current_timezone)

    original_run = mock_manager.run
    def mock_run(command, sudo=False):
        mock_manager.run_history.append((command, sudo))
        if command.startswith('test -f '):
            return CommandResult("", "", 0)
        if 'echo' in command and '/etc/timezone' in command:
            tz_state['tz'] = 'US/Pacific'
            return CommandResult("", "", 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run

    op = TimezoneOperation()
    record = op.apply(mock_manager, {"timezone": "US/Pacific"})

    assert record.changed is True
    assert record.errors == []

    # Test that echo ran
    assert any(cmd for cmd, _ in mock_manager.run_history if 'echo US/Pacific > /etc/timezone' in cmd)
    assert any(cmd for cmd, _ in mock_manager.run_history if 'ln -snf' in cmd and '/etc/localtime' in cmd)

def test_locale_operation_image(mock_manager, monkeypatch):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    # Setup
    mock_manager.write_file('/etc/default/locale', 'LANG=en_GB.UTF-8\n')

    loc_state = {'loc': 'en_GB.UTF-8'}
    def mock_get_current_locale(mgr):
        return loc_state['loc']
    monkeypatch.setattr(LocaleOperation, 'get_current_locale', mock_get_current_locale)

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        mock_manager.run_history.append((cmd, sudo))
        if 'raspi-config' in cmd or 'sed' in cmd or 'locale-gen' in cmd or 'update-locale' in cmd:
            loc_state['loc'] = 'en_US.UTF-8'
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = LocaleOperation()
    record = op.apply(mock_manager, {"locale": "en_US.UTF-8"})

    assert record.changed is True
    assert any(cmd for cmd, _ in mock_manager.run_history if 'raspi-config' in cmd or 'sed' in cmd or 'locale-gen' in cmd)

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_timezone_four_states(is_image, is_raspi, mock_manager, monkeypatch):
    mock_manager.is_os_image = lambda: is_image
    mock_manager.is_raspi_os = lambda: is_raspi

    def mock_get_current_timezone(mgr):
        return 'US/Eastern'
    monkeypatch.setattr(TimezoneOperation, 'get_current_timezone', mock_get_current_timezone)

    original_run = mock_manager.run
    def mock_run(command, sudo=False):
        if command.startswith('test -f '):
            return CommandResult("", "", 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run

    op = TimezoneOperation()
    op.apply(mock_manager, {'timezone': 'Europe/London'})
    history = [cmd for cmd, _ in mock_manager.run_history]

    if is_image:
        assert 'echo Europe/London > /etc/timezone' in history
        assert 'ln -snf /usr/share/zoneinfo/Europe/London /etc/localtime' in history
    elif is_raspi:
        assert 'raspi-config nonint do_change_timezone Europe/London' in history
    else:
        assert 'timedatectl set-timezone Europe/London' in history

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_locale_four_states(is_image, is_raspi, mock_manager, monkeypatch):
    mock_manager.is_os_image = lambda: is_image
    mock_manager.is_raspi_os = lambda: is_raspi

    mock_manager.mock_run_results["grep -E '^fr_FR.UTF-8( |$)' /usr/share/i18n/SUPPORTED"] = CommandResult("fr_FR.UTF-8 UTF-8\n", "", 0)

    loc_state = {'loc': 'en_GB.UTF-8'}
    def mock_get_current_locale(mgr):
        return loc_state['loc']
    monkeypatch.setattr(LocaleOperation, 'get_current_locale', mock_get_current_locale)

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        if 'raspi-config' in cmd or 'localectl' in cmd or 'locale-gen' in cmd or 'update-locale' in cmd:
            loc_state['loc'] = 'fr_FR.UTF-8'
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = LocaleOperation()
    op.apply(mock_manager, {'locale': 'fr_FR.UTF-8'})
    history = [cmd for cmd, _ in mock_manager.run_history]

    if is_image:
        assert 'locale-gen fr_FR.UTF-8' in history
        assert "printf '%s\\n' 'fr_FR.UTF-8 UTF-8' > /etc/locale.gen" in history
    elif is_raspi:
        assert 'raspi-config nonint do_change_locale fr_FR.UTF-8' in history
    else:
        assert 'localectl set-locale LANG=fr_FR.UTF-8' in history
