import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.hostname import HostnameOperation
from core.network import SSHOperation
from core.region import TimezoneOperation, LocaleOperation
from lib.managers import BaseManager, CommandResult

class MockFourOSStatesManager(BaseManager):
    def __init__(self, is_image: bool, is_raspi: bool):
        super().__init__()
        self._is_image = is_image
        self._is_raspi = is_raspi
        self.executed_commands = []
        self.sed_calls = []

    def is_os_image(self) -> bool:
        return self._is_image

    def is_raspi_os(self) -> bool:
        return self._is_raspi

    def file_exists(self, remotePath: str) -> bool:
        return True

    def dir_exists(self, remotePath: str) -> bool:
        return True

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        self.executed_commands.append(command)
        # Mock some outputs for gets
        if command == 'cat /etc/hostname':
            return CommandResult('testhost\n', '', 0)
        if command == 'systemctl is-enabled ssh':
            return CommandResult('enabled\n', '', 0)
        if command == 'timedatectl show --property=Timezone --value':
            return CommandResult('America/Chicago\n', '', 0)
        if command == 'cat /etc/timezone':
            return CommandResult('America/Chicago\n', '', 0)
        if command == 'localectl show --property=SystemLocale':
            return CommandResult('LANG=en_US.UTF-8\n', '', 0)
        if 'grep' in command and '/etc/default/locale' in command:
            return CommandResult('"en_US.UTF-8"\n', '', 0)
        if command == 'test -f /usr/share/zoneinfo/Europe/London':
            return CommandResult('', '', 0)
        if "grep -E '^fr_FR.UTF-8" in command:
            return CommandResult('fr_FR.UTF-8 UTF-8\n', '', 0)
        return CommandResult('', '', 0)

    def sed(self, remotePath: str, before: str, after: str, useRegex: bool = False, limit: int = 0, backup: str = '.bak', sudo: bool = False) -> None:
        self.sed_calls.append((remotePath, before, after))

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_hostname_four_states(is_image, is_raspi):
    mgr = MockFourOSStatesManager(is_image, is_raspi)
    op = HostnameOperation()

    # We don't care about the record for this test, we just want to verify what it executes.
    op.set_host(mgr, 'newhost')

    if is_image:
        assert ('/etc/hostname', 'testhost', 'newhost') in mgr.sed_calls
        assert ('/etc/hosts', 'testhost', 'newhost') in mgr.sed_calls
    elif is_raspi:
        assert 'raspi-config nonint do_hostname newhost' in mgr.executed_commands
    else:
        assert 'hostnamectl set-hostname newhost' in mgr.executed_commands
        assert ('/etc/hosts', 'testhost', 'newhost') in mgr.sed_calls

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_network_ssh_four_states(is_image, is_raspi):
    mgr = MockFourOSStatesManager(is_image, is_raspi)
    op = SSHOperation()

    op.set_ssh(mgr, 'disabled', 'enabled')

    if is_image and is_raspi:
        assert 'touch /boot/firmware/ssh' in mgr.executed_commands
    elif is_image and not is_raspi:
        assert 'ln -s /lib/systemd/system/ssh.service /etc/systemd/system/multi-user.target.wants/ssh.service' in mgr.executed_commands
    elif is_raspi:
        assert 'raspi-config nonint do_ssh 0' in mgr.executed_commands
    else:
        assert 'systemctl enable --now ssh' in mgr.executed_commands

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_timezone_four_states(is_image, is_raspi):
    mgr = MockFourOSStatesManager(is_image, is_raspi)
    op = TimezoneOperation()

    op.set_timezone(mgr, 'Europe/London')

    if is_image:
        assert 'echo Europe/London > /etc/timezone' in mgr.executed_commands
        assert 'ln -snf /usr/share/zoneinfo/Europe/London /etc/localtime' in mgr.executed_commands
    elif is_raspi:
        assert 'raspi-config nonint do_change_timezone Europe/London' in mgr.executed_commands
    else:
        assert 'timedatectl set-timezone Europe/London' in mgr.executed_commands

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_locale_four_states(is_image, is_raspi):
    mgr = MockFourOSStatesManager(is_image, is_raspi)
    op = LocaleOperation()

    op.set_locale(mgr, 'fr_FR.UTF-8')

    if is_image:
        assert 'locale-gen fr_FR.UTF-8' in mgr.executed_commands
        assert "printf '%s\\n' 'fr_FR.UTF-8 UTF-8' > /etc/locale.gen" in mgr.executed_commands
    elif is_raspi:
        assert 'raspi-config nonint do_change_locale fr_FR.UTF-8' in mgr.executed_commands
    else:
        assert 'localectl set-locale LANG=fr_FR.UTF-8' in mgr.executed_commands

