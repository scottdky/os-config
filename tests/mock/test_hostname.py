import pytest
from core.hostname import HostnameOperation, UsernameOperation, PasswordOperation
from lib.managers.base import CommandResult

def test_hostname_operation_offline_image(mock_manager):
    # Mock offline image
    mock_manager.is_os_image = lambda: True

    mock_manager.write_file('/etc/hostname', 'oldhost\n')
    mock_manager.write_file('/etc/hosts', '127.0.0.1\tlocalhost\n127.0.1.1\toldhost\n')

    op = HostnameOperation()
    record = op.apply(mock_manager, {"hostname": "newhost"})
    assert record.changed is True
    assert mock_manager.read_file('/etc/hostname').strip() == 'newhost'
    assert 'newhost' in mock_manager.read_file('/etc/hosts')
    assert 'oldhost' not in mock_manager.read_file('/etc/hosts')

    # Test idempotency
    record = op.apply(mock_manager, {"hostname": "newhost"})
    assert record.changed is False

def test_hostname_operation_live_pi(mock_manager):
    mock_manager.is_os_image = lambda: False
    mock_manager.is_raspi_os = lambda: True

    # Mock current hostname command
    mock_manager.mock_run_results['cat /etc/hostname'] = CommandResult('oldhost\n', '', 0)

    op = HostnameOperation()
    record = op.apply(mock_manager, {"hostname": "newhost"})

    # We expect raspi-config to have been run
    assert any(cmd for cmd, _ in mock_manager.run_history if 'raspi-config nonint do_hostname newhost' in cmd)
    # The manager's sed commands for hostname might not run directly inside if live pi, it relies on raspi-config
    # Our mock cat still returns 'oldhost', so the verify check will fail and mark it as error, but let's change mock run results
    # so the verification passes.

def test_hostname_operation_live_pi_verify(mock_manager):
    mock_manager.is_os_image = lambda: False
    mock_manager.is_raspi_os = lambda: True

    call_count = [0]
    def mock_run(command, sudo=False):
        if command == 'cat /etc/hostname':
            call_count[0] += 1
            if call_count[0] == 1:
                return CommandResult('oldhost\n', '', 0)
            else:
                return CommandResult('newhost\n', '', 0)
        return CommandResult('', '', 0)

    mock_manager.run = mock_run

    op = HostnameOperation()
    record = op.apply(mock_manager, {"hostname": "newhost"})
    assert record.changed is True
    assert not record.errors

def test_username_operation(mock_manager):
    # Mock getent passwd
    mock_manager.mock_run_results["getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'"] = CommandResult("olduser\n", "", 0)

    op = UsernameOperation()
    record = op.apply(mock_manager, {"username": "newuser"})

    assert record.changed is True
    assert any(cmd for cmd, _ in mock_manager.run_history if 'usermod -m -l newuser -d /home/newuser olduser' in cmd)

    # Idempotency
    mock_manager.mock_run_results["getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'"] = CommandResult("newuser\n", "", 0)
    record2 = op.apply(mock_manager, {"username": "newuser"})
    assert record2.changed is False

def test_password_operation(mock_manager):
    mock_manager.mock_run_results["getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'"] = CommandResult("testuser\n", "", 0)

    op = PasswordOperation()
    record = op.apply(mock_manager, {"password": "newpass"})

    assert record.changed is True
    assert any(cmd for cmd, _ in mock_manager.run_history if "echo 'testuser:newpass' | chpasswd" in cmd)
    # Passwords don't have standard idempotency checks via chpasswd

@pytest.mark.parametrize("is_image,is_raspi", [(True, True), (True, False), (False, True), (False, False)])
def test_hostname_four_states(is_image, is_raspi, mock_manager):
    mock_manager.is_os_image = lambda: is_image
    mock_manager.is_raspi_os = lambda: is_raspi

    mock_manager.write_file('/etc/hostname', 'testhost\n')
    mock_manager.write_file('/etc/hosts', '127.0.1.1\ttesthost\n')

    # Mock cat so we ensure it doesn't fail on verify
    original_run = mock_manager.run
    call_count = [0]
    def mock_run(command, sudo=False):
        if command == 'cat /etc/hostname':
            call_count[0] += 1
            if call_count[0] == 1:
                return CommandResult('testhost\n', '', 0)
            return CommandResult('newhost\n', '', 0)
        return original_run(command, sudo=sudo)
    mock_manager.run = mock_run

    op = HostnameOperation()
    op.apply(mock_manager, {"hostname": "newhost"})

    history = [cmd for cmd, _ in mock_manager.run_history]

    if is_image:
        assert mock_manager.read_file('/etc/hostname').strip() == 'newhost'
        assert 'newhost' in mock_manager.read_file('/etc/hosts')
    elif is_raspi:
        assert 'raspi-config nonint do_hostname newhost' in history
    else:
        assert 'hostnamectl set-hostname newhost' in history
        # verify sed also fired for hosts
        assert 'newhost' in mock_manager.read_file('/etc/hosts')
