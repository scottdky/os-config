import pytest
from unittest.mock import MagicMock
from lib.managers.base import BaseManager

class DummyManager(BaseManager):
    """A minimal concrete implementation of BaseManager for testing."""
    def __init__(self):
        super().__init__()
        self.exists = MagicMock()
        self.read_file = MagicMock()
        self.write_file = MagicMock()
        self.put = MagicMock()
        self.run = MagicMock()

def test_enable_when_missing():
    mgr = DummyManager()
    mgr.exists.return_value = False

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True)

    # file didn't exist, so no backup should be attempted, just the new line written.
    mgr.write_file.assert_called_once_with('/etc/test.conf', 'key=value\n', sudo=False)

def test_enable_when_commented():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "#key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='.bak')

    # File gets backed up, then updated
    assert mgr.write_file.call_count == 2
    mgr.write_file.assert_any_call('/etc/test.conf.bak', '#key=value\nother=thing', sudo=False)
    mgr.write_file.assert_any_call('/etc/test.conf', 'key=value\nother=thing\n', sudo=False)

def test_enable_when_already_enabled():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True)

    # No modifications, so write_file shouldn't be called
    mgr.write_file.assert_not_called()

def test_disable_when_missing():
    mgr = DummyManager()
    mgr.exists.return_value = False

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False)

    # Missing but want it disabled -> no action taken
    mgr.write_file.assert_not_called()

def test_disable_when_enabled():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False, backup='.bak')

    assert mgr.write_file.call_count == 2
    mgr.write_file.assert_any_call('/etc/test.conf.bak', 'key=value\nother=thing', sudo=False)
    mgr.write_file.assert_any_call('/etc/test.conf', '#key=value\nother=thing\n', sudo=False)

def test_disable_when_already_disabled():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "#key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False)

    # No modifications needed
    mgr.write_file.assert_not_called()

def test_no_backup_flag():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "#key=value"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='')

    # Only one call: the main file write, no backup write
    mgr.write_file.assert_called_once_with('/etc/test.conf', 'key=value\n', sudo=False)

def test_sudo_flag_is_passed():
    mgr = DummyManager()
    mgr.exists.return_value = False

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, sudo=True)

    mgr.write_file.assert_called_once_with('/etc/test.conf', 'key=value\n', sudo=True)

def test_handles_whitespace_gracefully():
    mgr = DummyManager()
    mgr.exists.return_value = True
    # Spaces before # and before/after the variable
    mgr.read_file.return_value = "  #   key=value  \nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='')

    # Only the parsed line is updated, keeping the rest of the file structure
    mgr.write_file.assert_called_once_with('/etc/test.conf', 'key=value\nother=thing\n', sudo=False)
def test_backup_only_once_per_file():
    mgr = DummyManager()
    mgr.exists.return_value = True
    mgr.read_file.return_value = "#key1=v1\n#key2=v2\n"

    # First operation on the file
    mgr.set_config_line('/etc/multiple.conf', 'key1=v1', enable=True, backup='.bak')

    # verify backup logic was triggered and original stored
    mgr.write_file.assert_any_call('/etc/multiple.conf.bak', '#key1=v1\n#key2=v2\n', sudo=False)

    # Reset mock and update file content for second operation
    mgr.write_file.reset_mock()
    mgr.read_file.return_value = "key1=v1\n#key2=v2\n"

    # Second operation on the same file
    mgr.set_config_line('/etc/multiple.conf', 'key2=v2', enable=True, backup='.bak')

    # Verify the backup was skipped on the second run because it is tracked in `_backed_up_files`
    assert 'multiple.conf.bak' not in str(mgr.write_file.mock_calls)
    mgr.write_file.assert_called_once_with('/etc/multiple.conf', 'key1=v1\nkey2=v2\n', sudo=False)

def test_get_boot_config_path_bookworm():
    mgr = DummyManager()
    mgr.exists.side_effect = lambda path: path == '/boot/firmware/config.txt'
    assert mgr.get_boot_config_path() == '/boot/firmware/config.txt'

def test_get_boot_config_path_bullseye():
    mgr = DummyManager()
    mgr.exists.side_effect = lambda path: path == '/boot/config.txt'
    assert mgr.get_boot_config_path() == '/boot/config.txt'

def test_get_boot_config_path_not_found():
    mgr = DummyManager()
    mgr.exists.return_value = False
    with pytest.raises(FileNotFoundError, match="Could not locate Raspberry Pi config.txt"):
        mgr.get_boot_config_path()
