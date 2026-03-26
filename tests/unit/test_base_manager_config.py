import pytest
from lib.managers.base import BaseManager

class DummyManager(BaseManager):
    """A minimal concrete implementation of BaseManager for testing."""
    def __init__(self):
        super().__init__()
        self.exists_mock = lambda path: False
        self.read_file_mock = lambda path, sudo=False: ""
        self.write_file_calls = []

    def exists(self, path):
        return self.exists_mock(path)

    def read_file(self, path, sudo=False):
        return self.read_file_mock(path, sudo)

    def write_file(self, path, content, sudo=False):
        self.write_file_calls.append((path, content, sudo))

    def put(self, source, destination, sudo=False):
        pass

    def run(self, command, sudo=False, **kwargs):
        pass


def test_enable_when_missing():
    mgr = DummyManager()
    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True)

    assert len(mgr.write_file_calls) == 1
    assert mgr.write_file_calls[0] == ('/etc/test.conf', 'key=value\n', False)

def test_enable_when_commented():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "#key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='.bak')

    assert len(mgr.write_file_calls) == 2
    assert mgr.write_file_calls[0] == ('/etc/test.conf.bak', '#key=value\nother=thing', False)
    assert mgr.write_file_calls[1] == ('/etc/test.conf', 'key=value\nother=thing\n', False)

def test_enable_when_already_enabled():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True)

    assert len(mgr.write_file_calls) == 0

def test_disable_when_missing():
    mgr = DummyManager()
    
    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False)

    assert len(mgr.write_file_calls) == 0

def test_disable_when_enabled():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False, backup='.bak')
    
    assert len(mgr.write_file_calls) == 2
    assert mgr.write_file_calls[0] == ('/etc/test.conf.bak', 'key=value\nother=thing', False)
    assert mgr.write_file_calls[1] == ('/etc/test.conf', '#key=value\nother=thing\n', False)

def test_disable_when_already_disabled():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "#key=value\nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=False)

    assert len(mgr.write_file_calls) == 0

def test_no_backup_flag():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "#key=value"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='')

    assert len(mgr.write_file_calls) == 1
    assert mgr.write_file_calls[0] == ('/etc/test.conf', 'key=value\n', False)

def test_sudo_flag_is_passed():
    mgr = DummyManager()
    
    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, sudo=True)

    assert len(mgr.write_file_calls) == 1
    assert mgr.write_file_calls[0] == ('/etc/test.conf', 'key=value\n', True)

def test_handles_whitespace_gracefully():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "  #   key=value  \nother=thing"

    mgr.set_config_line('/etc/test.conf', 'key=value', enable=True, backup='')

    assert len(mgr.write_file_calls) == 1
    assert mgr.write_file_calls[0] == ('/etc/test.conf', 'key=value\nother=thing\n', False)

def test_backup_only_once_per_file():
    mgr = DummyManager()
    mgr.exists_mock = lambda p: True
    mgr.read_file_mock = lambda p, s: "#key1=v1\n#key2=v2\n"

    mgr.set_config_line('/etc/multiple.conf', 'key1=v1', enable=True, backup='.bak')
    
    assert len(mgr.write_file_calls) == 2
    assert mgr.write_file_calls[0] == ('/etc/multiple.conf.bak', '#key1=v1\n#key2=v2\n', False)
    
    mgr.write_file_calls = []
    mgr.read_file_mock = lambda p, s: "key1=v1\n#key2=v2\n"
    
    mgr.set_config_line('/etc/multiple.conf', 'key2=v2', enable=True, backup='.bak')
    
    assert len(mgr.write_file_calls) == 1
    assert mgr.write_file_calls[0] == ('/etc/multiple.conf', 'key1=v1\nkey2=v2\n', False)

def test_get_boot_file_path_bookworm():
    mgr = DummyManager()
    mgr.exists_mock = lambda path: path == '/boot/firmware/config.txt'

    assert mgr.get_boot_file_path('config.txt') == '/boot/firmware/config.txt'

def test_get_boot_file_path_bullseye():
    mgr = DummyManager()
    mgr.exists_mock = lambda path: path == '/boot/config.txt'
    
    assert mgr.get_boot_file_path('config.txt') == '/boot/config.txt'

def test_get_boot_file_path_not_found():
    mgr = DummyManager()
    
    with pytest.raises(FileNotFoundError, match="Could not locate Raspberry Pi config.txt"):
        mgr.get_boot_file_path('config.txt')
