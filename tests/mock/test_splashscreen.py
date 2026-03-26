import pytest
from pathlib import Path
from core.splashscreen import SplashscreenOperation
from lib.managers.base import CommandResult
from lib.operations import OperationAbortedError

def test_splashscreen_prompt_missing(mock_manager, monkeypatch):
    op = SplashscreenOperation()

    # Needs valid image path on the host system to pass local file check
    # Let's create a fake image on the host or mock os.path.isfile
    monkeypatch.setattr('os.path.isfile', lambda p: True)

    # Mock inputs
    inputs = iter(['/path/to/my/image.png'])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    result = op.prompt_missing_values(mock_manager, {'image_path': {}}, {})
    assert result == {'image_path': '/path/to/my/image.png'}

def test_splashscreen_prompt_aborted(mock_manager, monkeypatch):
    op = SplashscreenOperation()
    monkeypatch.setattr('os.path.isfile', lambda p: False)

    inputs = iter([''])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    with pytest.raises(OperationAbortedError, match="No image path provided and no existing image found"):
        op.prompt_missing_values(mock_manager, {'image_path': {}}, {})

def test_splashscreen_apply(mock_manager, monkeypatch):
    op = SplashscreenOperation()

    # We don't have to mock `os.path.isfile` here because `apply` doesn't check it;
    # it just calls `mgr.put()`, but we SHOULD put an empty cmdline.txt because loadCmdlineFile expects one.
    mock_manager.write_file('/boot/firmware/cmdline.txt', 'console=tty1 root=PARTUUID=1234\n')
    mock_manager.write_file('/boot/firmware/config.txt', '')

    # Mock manager doesn't run systemd_enable normally, but BaseManager implements it via `run(systemctl)` and `ln -s`

    # mock put for file
    original_put = mock_manager.put
    def mock_put(local_path, remote_path, sudo=False):
        if local_path == '/fake/host/path.png':
            mock_manager.write_file(remote_path, 'fake_png_data')
        else:
            original_put(local_path, remote_path, sudo=sudo)

    monkeypatch.setattr(mock_manager, 'put', mock_put)

    record = op.apply(mock_manager, {'image_path': '/fake/host/path.png'})

    assert record.changed is True

    # Verify cmdline was updated
    cmdline = mock_manager.read_file('/boot/firmware/cmdline.txt')
    assert 'quiet' in cmdline
    assert 'splash' in cmdline
    assert 'vt.global_cursor_default=0' in cmdline

    # Verify config was updated
    config = mock_manager.read_file('/boot/firmware/config.txt')
    assert 'disable_splash=1' in config

    # Verify files created
    assert mock_manager.exists('/usr/share/plymouth/themes/custom-splash/custom-splash.plymouth')
    assert mock_manager.exists('/usr/share/plymouth/themes/custom-splash/custom-splash.script')

    # Verify install script and service were deployed
    assert mock_manager.exists('/usr/local/bin/splashscreen_install.sh')
    assert mock_manager.exists('/etc/systemd/system/splashscreen_install.service')
