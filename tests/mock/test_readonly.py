import pytest
import os
from pathlib import Path
from core.readonly import ReadonlyOperation
from lib.managers.base import CommandResult

def test_readonly_operation(mock_manager):
    mock_manager.is_os_image = lambda: True
    mock_manager.is_raspi_os = lambda: True

    # Create some files it expects to configure/test
    mock_manager.write_file('/etc/fstab', 'proc /proc proc defaults 0 0\n')
    mock_manager.write_file('/var/lib/dhcp', 'dhcpdata')
    mock_manager.write_file('/home/pi/.bashrc', '# bashrc')

    Path(mock_manager.tmp_path, 'var/spool/cron').mkdir(parents=True, exist_ok=True)

    # Setup local resources needed
    base_path = Path('core/resources')
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / 'bash_prompt.py').write_text('prompt_script', encoding='utf-8')
    (base_path / 'enable_ro_fs.py').write_text('ro_script', encoding='utf-8')
    (base_path / 'enable-ro-fs.service').write_text('ro_service', encoding='utf-8')

    original_run = mock_manager.run
    installed_pkgs = set(['dphys-swapfile']) # It will see this and run swapoff

    def mock_run(command, sudo=False):
        if command.startswith("dpkg-query -W -f='${Status}'"):
            pkg = command.split()[-2].strip("'")
            if pkg in installed_pkgs:
                return CommandResult("install ok installed", "", 0)
            return CommandResult("", "", 0)

        # Override test -L appropriately
        if command.startswith("test -L "):
            path = command.split()[-1]
            if path in mock_manager._resolve_path(''):
                pass
            return CommandResult("", "", 1) # Return 1 (false) so it creates the symlink

        return original_run(command, sudo)

    mock_manager.run = mock_run

    op = ReadonlyOperation()
    record = op.apply(mock_manager, {})

    assert record.changed is True
    assert not record.errors

    # Check that swapoff ran
    assert any(cmd for cmd, _ in mock_manager.run_history if 'dphys-swapfile swapoff' in cmd)

    # Check that it installed some packages
    assert any(cmd for cmd, _ in mock_manager.run_history if 'apt-get install -y busybox-syslogd' in cmd)

    # Check fstab added tmpfs
    fstab_content = mock_manager.read_file('/etc/fstab')
    assert 'tmpfs\t/tmp\ttmpfs' in fstab_content
    assert 'tmpfs\t/var/log\ttmpfs' in fstab_content

    # Check custom bash prompt added
    bashrc_content = mock_manager.read_file('/home/pi/.bashrc')
    assert 'prompt_command' in bashrc_content

    # Test idempotency (partially, because we don't correctly sim 'test -L' resolving to true the second time, but let's see)
    def mock_run_idempotent(command, sudo=False):
        if command.startswith("dpkg-query -W -f='${Status}'"):
            pkg = command.split()[-2].strip("'")
            if pkg in ['busybox-syslogd', 'chrony']:
                return CommandResult("install ok installed", "", 0)
            return CommandResult("", "", 0) # Not installed for those it removed
        if command.startswith("test -L "):
            return CommandResult("", "", 0) # Already a symlink
        return original_run(command, sudo)

    mock_manager.run = mock_run_idempotent
    record2 = op.apply(mock_manager, {})
    assert record2.changed is False
