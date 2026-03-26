import pytest
from core.network import SSHOperation, WiFiOperation
from lib.managers.base import CommandResult

def test_ssh_operation_image_raspi(mock_manager):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    # mock exists properly
    _files = set(['/boot/firmware'])
    mock_manager.exists = lambda path: path in _files

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        mock_manager.run_history.append((cmd, sudo))
        if cmd == 'touch /boot/firmware/ssh':
            _files.add('/boot/firmware/ssh')
            return CommandResult("", "", 0)
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = SSHOperation()

    # Not enabled yet
    record = op.apply(mock_manager, {"ssh": "enabled"})
    assert record.changed is True
    assert any(cmd for cmd, _ in mock_manager.run_history if 'touch /boot/firmware/ssh' in cmd)

    # Idempotency
    record2 = op.apply(mock_manager, {"ssh": "enabled"})
    assert record2.changed is False

def test_ssh_operation_disable(mock_manager):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    _files = set(['/boot/firmware', '/boot/firmware/ssh'])
    mock_manager.exists = lambda path: path in _files

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        mock_manager.run_history.append((cmd, sudo))
        if 'rm -f' in cmd and '/boot/firmware/ssh' in cmd:
            if '/boot/firmware/ssh' in _files:
                _files.remove('/boot/firmware/ssh')
            return CommandResult("", "", 0)
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = SSHOperation()
    record = op.apply(mock_manager, {"ssh": "disabled"})

    assert record.changed is True
    assert any(cmd for cmd, _ in mock_manager.run_history if 'rm -f /boot/firmware/ssh' in cmd)

def test_wifi_operation_image_raspi(mock_manager):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    mock_manager.exists = lambda path: path == '/boot/firmware'

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        if cmd.startswith('grep '):
            return CommandResult("", "", 1) # Return failure so it thinks no country yet
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = WiFiOperation()
    configs = {
        "wifi_country": "US",
        "wifi_ssid": "TestNetwork",
        "wifi_password": "TestPassword"
    }

    record = op.apply(mock_manager, configs)
    assert record.changed is True

    # We should see printf used to create wpa_supplicant.conf
    printf_cmd = next((cmd for cmd, _ in mock_manager.run_history if 'printf' in cmd and 'wpa_supplicant.conf' in cmd), None)
    assert printf_cmd is not None
    assert 'country=US' in printf_cmd
    assert 'ssid="TestNetwork"' in printf_cmd
    assert 'psk="TestPassword"' in printf_cmd

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_network_ssh_four_states(is_image, is_raspi, mock_manager):
    mock_manager.is_os_image = lambda: is_image
    mock_manager.is_raspi_os = lambda: is_raspi

    original_run = mock_manager.run
    def mock_run(command, sudo=False):
        if command == 'systemctl is-enabled ssh':
            return CommandResult('disabled\n', '', 1)
        if command == 'systemctl is-active ssh':
            return CommandResult('inactive\n', '', 1)
        if command == 'raspi-config nonint get_ssh':
            return CommandResult('1\n', '', 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run

    op = SSHOperation()
    op.apply(mock_manager, {"ssh": "enabled"})
    history = [cmd for cmd, _ in mock_manager.run_history]

    if is_image and is_raspi:
        assert 'touch /boot/firmware/ssh' in history
    elif is_image and not is_raspi:
        assert 'ln -s /lib/systemd/system/ssh.service /etc/systemd/system/multi-user.target.wants/ssh.service' in history
    elif is_raspi:
        assert 'raspi-config nonint do_ssh 0' in history
    else:
        assert 'systemctl enable --now ssh' in history

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_network_wifi_four_states(is_image, is_raspi, mock_manager):
    mock_manager.is_os_image = lambda: is_image
    mock_manager.is_raspi_os = lambda: is_raspi

    original_run = mock_manager.run
    def mock_run(cmd, sudo=False):
        if cmd.startswith('grep ') and 'country=' in cmd:
            return CommandResult("", "", 1)
        if cmd == 'raspi-config nonint get_wifi_country':
            return CommandResult("", "", 1)
        if cmd == 'iw reg get | grep "country" | head -n 1':
            return CommandResult("", "", 1)
        return original_run(cmd, sudo)
    mock_manager.run = mock_run

    op = WiFiOperation()
    op.apply(mock_manager, {"wifi_country": "US", "wifi_ssid": "Test-Network", "wifi_password": "supersecret"})
    history = [cmd for cmd, _ in mock_manager.run_history]

    if is_image and is_raspi:
        assert any('printf' in cmd and '/boot/firmware/wpa_supplicant.conf' in cmd for cmd in history)
    elif is_image and not is_raspi:
        assert any('printf' in cmd and '/etc/NetworkManager/system-connections/Test-Network.nmconnection' in cmd for cmd in history)
    elif is_raspi:
        assert 'raspi-config nonint do_wifi_country US' in history
        assert 'raspi-config nonint do_wifi_ssid_passphrase Test-Network supersecret' in history
    else:
        assert 'iw reg set US' in history
        assert 'nmcli device wifi connect Test-Network password supersecret' in history

