"""Mock tests for operation-level structured log records."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.hostname import HostnameOperation, PasswordOperation, UsernameOperation
from core.region import LocaleOperation, TimezoneOperation
from lib.managers import BaseManager, CommandResult


class _FakeOperationManager(BaseManager):
    """State-driven manager mock for operation record tests."""

    def __init__(self) -> None:
        super().__init__()
        self.hostname = 'oldhost'
        self.userName = 'pi'
        self.timezone = 'America/Chicago'
        self.locale = 'en_US.UTF-8'
        self.supportedTimezones = {
            '/usr/share/zoneinfo/America/Chicago',
            '/usr/share/zoneinfo/America/Los_Angeles',
        }
        self.supportedLocales = {
            'en_US.UTF-8 UTF-8',
            'en_GB.UTF-8 UTF-8',
        }
        self.failUsermod = False
        self.failChpasswd = False

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        _ = sudo
        if command == 'cat /etc/hostname':
            return CommandResult(f'{self.hostname}\n', '', 0)

        if command.startswith('getent passwd | awk -F:'):
            return CommandResult(f'{self.userName}\n', '', 0)

        usermodMatch = re.match(r'^usermod -m -l (\S+) -d /home/\1 (\S+)$', command)
        if usermodMatch:
            if self.failUsermod:
                return CommandResult('', 'usermod failed', 1)
            newUser = usermodMatch.group(1)
            oldUser = usermodMatch.group(2)
            if oldUser == self.userName:
                self.userName = newUser
                return CommandResult('', '', 0)
            return CommandResult('', 'user not found', 1)

        if command.startswith("echo '") and command.endswith("' | chpasswd"):
            if self.failChpasswd:
                return CommandResult('', 'chpasswd failed', 1)
            return CommandResult('', '', 0)

        timezoneCheck = re.match(r'^test -f (.+)$', command)
        if timezoneCheck:
            path = timezoneCheck.group(1)
            return CommandResult('', '', 0 if path in self.supportedTimezones else 1)

        if command == 'cat /etc/timezone':
            return CommandResult(f'{self.timezone}\n', '', 0)

        timezoneWrite = re.match(r'^echo (.+) > /etc/timezone$', command)
        if timezoneWrite:
            value = timezoneWrite.group(1).strip().strip("'")
            self.timezone = value
            return CommandResult('', '', 0)

        timezoneLink = re.match(r'^ln -snf (.+) /etc/localtime$', command)
        if timezoneLink:
            return CommandResult('', '', 0)

        localeSupported = re.match(r"^grep -E '\^(.+)\( \|\$\)' /usr/share/i18n/SUPPORTED$", command)
        if localeSupported:
            requestedLocale = localeSupported.group(1)
            matchingLine = next((line for line in self.supportedLocales if line.startswith(requestedLocale + ' ')), '')
            if matchingLine:
                return CommandResult(f'{matchingLine}\n', '', 0)
            return CommandResult('', '', 1)

        if command.startswith('if [ -L /etc/locale.gen ]'):
            return CommandResult('', '', 0)

        localeGenWrite = re.match(r"^printf '%s\\n' '(.+)' > /etc/locale.gen$", command)
        if localeGenWrite:
            return CommandResult('', '', 0)

        localeGenerate = re.match(r'^locale-gen (.+)$', command)
        if localeGenerate:
            return CommandResult('', '', 0)

        if command == 'update-locale --no-checks LANG':
            return CommandResult('', '', 0)

        localeSet = re.match(r'^update-locale --no-checks LANG=(.+)$', command)
        if localeSet:
            value = localeSet.group(1).strip().strip("'")
            self.locale = value
            return CommandResult('', '', 0)

        if command == "grep '^LANG=' /etc/default/locale | cut -d= -f2":
            return CommandResult(f'"{self.locale}"\n', '', 0)

        if command == "grep '^LANG=' /etc/locale.conf | cut -d= -f2":
            return CommandResult('', '', 1)

        return CommandResult('', f'unsupported command: {command}', 1)

    def exists(self, remotePath: str) -> bool:
        _ = remotePath
        return True

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        _ = localPath, remotePath, sudo
        return

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        _ = remotePath, localPath, sudo
        return

    def sed(self, remotePath: str, before: str, after: str, useRegex: bool = False,
            limit: int = 0, backup: str = '.bak', sudo: bool = False) -> None:
        _ = remotePath, before, after, useRegex, limit, backup, sudo
        self.hostname = after


@pytest.mark.mock
def test_hostname_record_contains_previous_and_current_state():
    """Hostname operation should return changed record with old/new state."""
    mgr = _FakeOperationManager()
    operation = HostnameOperation()

    record = operation.set_host(mgr, 'newhost')

    assert record.changed is True
    assert record.previousState == 'oldhost'
    assert record.currentState == 'newhost'
    assert record.errors == []


@pytest.mark.mock
def test_username_record_contains_error_on_failure():
    """Username operation should include command error in record."""
    mgr = _FakeOperationManager()
    operation = UsernameOperation()
    mgr.failUsermod = True

    record = operation.set_user(mgr, 'pi', 'newuser')

    assert record.changed is False
    assert record.previousState == 'pi'
    assert record.currentState == 'pi'
    assert len(record.errors) == 1
    assert 'usermod failed' in record.errors[0]


@pytest.mark.mock
def test_password_record_redacts_secret_state():
    """Password operation should avoid storing plaintext password in record."""
    mgr = _FakeOperationManager()
    operation = PasswordOperation()

    record = operation.set_pass(mgr, 'pi', 'supersecret')

    assert record.changed is True
    assert isinstance(record.previousState, dict)
    assert isinstance(record.currentState, dict)
    assert record.previousState['password'] == '<redacted>'
    assert record.currentState['password'] == '<updated>'
    assert record.errors == []


@pytest.mark.mock
def test_timezone_record_handles_no_change():
    """Timezone operation should produce no-change record when already set."""
    mgr = _FakeOperationManager()
    operation = TimezoneOperation()

    record = operation.set_timezone(mgr, 'America/Chicago')

    assert record.changed is False
    assert record.previousState == 'America/Chicago'
    assert record.currentState == 'America/Chicago'
    assert record.errors == []


@pytest.mark.mock
def test_locale_record_handles_unsupported_locale():
    """Locale operation should include error when locale is unsupported."""
    mgr = _FakeOperationManager()
    operation = LocaleOperation()

    record = operation.set_locale(mgr, 'fr_FR.UTF-8')

    assert record.changed is False
    assert record.previousState == 'en_US.UTF-8'
    assert record.currentState == 'en_US.UTF-8'
    assert len(record.errors) == 1
    assert 'not found' in record.errors[0]
