import pytest
from lib.managers.factory import create_manager, interactive_create_manager
from lib.managers.local import LocalManager
from lib.managers.remote import SSHManager
from lib.managers.image import ImageFileManager, SDCardManager

from lib.managers.base import CommandResult

@pytest.fixture(autouse=True)
def mock_sudo_validation(monkeypatch):
    monkeypatch.setattr('lib.managers.base.BaseManager.validate_sudo', lambda self: CommandResult("", "", 0))

def test_create_manager_local():
    mgr = create_manager('local')
    assert isinstance(mgr, LocalManager)

def test_create_manager_ssh():
    mgr = create_manager('ssh', hostName='testhost', userName='user')
    assert isinstance(mgr, SSHManager)
    assert mgr.connect_kwargs['hostname'] == 'testhost'
    assert mgr.connect_kwargs['username'] == 'user'

def test_create_manager_image():
    mgr = create_manager('image', imagePath='/path/to/img.img', mountPath='/mnt/custom')
    assert isinstance(mgr, ImageFileManager)
    assert mgr.imagePath == '/path/to/img.img'
    assert mgr.mountPath == '/mnt/custom'

def test_create_manager_sdcard():
    mgr = create_manager('sdcard', devicePath='/dev/sdX', mountPath='/mnt/custom')
    assert isinstance(mgr, SDCardManager)
    assert mgr.devicePath == '/dev/sdX'
    assert mgr.mountPath == '/mnt/custom'

def test_create_manager_sdcard_interactive(monkeypatch):
    mock_sd = type('MockSDCardManager', (), {})()
    monkeypatch.setattr(SDCardManager, 'from_interactive_selection', lambda **kw: mock_sd)
    mgr = create_manager('sdcard', interactive=True)
    assert mgr is mock_sd

def test_create_manager_invalid():
    with pytest.raises(ValueError, match="Unknown mode"):
        create_manager('invalid')

def test_interactive_create_manager_exit(monkeypatch):
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: None)
    assert interactive_create_manager() is None

def test_interactive_create_manager_local(monkeypatch):
    selections = iter([0])
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: next(selections))
    mgr = interactive_create_manager()
    assert isinstance(mgr, LocalManager)

def test_interactive_create_manager_ssh(monkeypatch):
    selections = iter([1])
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: next(selections))
    
    inputs = iter(['myhost', 'myuser', '', ''])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    mgr = interactive_create_manager()
    assert isinstance(mgr, SSHManager)
    assert mgr.connect_kwargs['hostname'] == 'myhost'
    assert mgr.connect_kwargs['username'] == 'myuser'

def test_interactive_create_manager_image(monkeypatch):
    selections = iter([2])
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: next(selections))
    
    inputs = iter(['/path/to.img', '/mnt/tmp'])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    mgr = interactive_create_manager()
    assert isinstance(mgr, ImageFileManager)
    assert mgr.imagePath == '/path/to.img'
    assert mgr.mountPath == '/mnt/tmp'

def test_interactive_create_manager_sdcard_auto(monkeypatch):
    selections = iter([3, 0])
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: next(selections))
    
    mock_sd = type('MockSDCardManager', (), {})()
    monkeypatch.setattr(SDCardManager, 'from_interactive_selection', lambda **kw: mock_sd)
    
    mgr = interactive_create_manager()
    assert mgr is mock_sd

def test_interactive_create_manager_sdcard_manual(monkeypatch):
    selections = iter([3, 1])
    monkeypatch.setattr('lib.managers.factory.get_single_selection', lambda *a, **kw: next(selections))
    
    inputs = iter(['/dev/sdX', '/mnt/custom'])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    mgr = interactive_create_manager()
    assert isinstance(mgr, SDCardManager)
    assert mgr.devicePath == '/dev/sdX'
    assert mgr.mountPath == '/mnt/custom'
