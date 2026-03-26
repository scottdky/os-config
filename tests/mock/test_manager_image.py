import pytest
import os
import stat
from lib.managers.image import ImageFileManager
from lib.managers.base import CommandResult

@pytest.fixture
def mock_image_manager(monkeypatch):
    """Fixture providing a partially mocked ImageFileManager."""
    # Prevent sudo validation and target validation from actually firing
    monkeypatch.setattr(ImageFileManager, 'validate_sudo', lambda self: CommandResult('', '', 0))
    monkeypatch.setattr(ImageFileManager, '_validate_target', lambda self: None)
    monkeypatch.setattr(ImageFileManager, '_perform_mount', lambda self: None)
    
    manager = ImageFileManager(imagePath="/path/to/my_image.img", mountPath="/tmp/test")
    return manager


# --- Preflight Mountability Tests ---

def test_preflight_rejects_network_backed_image(mock_image_manager, monkeypatch):
    """Network-backed image paths should fail before losetup probe."""
    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, 'run_local', lambda cmd, sudo=False: CommandResult('', '', 0))
    
    with pytest.raises(RuntimeError, match='network-backed filesystem'):
        mock_image_manager._preflight_mountability('/mnt/network/image.img')

def test_preflight_rejects_when_losetup_probe_fails(mock_image_manager, monkeypatch):
    """Losetup probe failures should raise actionable runtime errors."""
    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: False)
    monkeypatch.setattr(mock_image_manager, 'run_local', lambda cmd, sudo=False: CommandResult('', 'losetup failed', 1))
    
    with pytest.raises(RuntimeError, match='Mountability probe failed'):
        mock_image_manager._preflight_mountability('/tmp/image.img')

def test_preflight_detaches_probe_loop_device_on_success(mock_image_manager, monkeypatch):
    """Successful probes should detach temporary loop device."""
    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: False)
    commands = []

    def mock_run_local(command: str, sudo: bool = False) -> CommandResult:
        commands.append((command, sudo))
        if command.startswith('losetup -f --show --read-only'):
            return CommandResult('/dev/loop7\n', '', 0)
        if command == 'losetup -d /dev/loop7':
            return CommandResult('', '', 0)
        return CommandResult('', '', 1)

    monkeypatch.setattr(mock_image_manager, 'run_local', mock_run_local)

    mock_image_manager._preflight_mountability('/tmp/image.img')

    assert commands == [
        ('losetup -f --show --read-only /tmp/image.img', True),
        ('losetup -d /dev/loop7', True),
    ]


# --- Staging Policy Tests ---

def test_local_path_skips_staging(mock_image_manager, monkeypatch, tmp_path):
    """Local filesystem image path should mount directly without staging."""
    imagePath = tmp_path / 'local.img'
    imagePath.write_bytes(b'test')
    
    mock_image_manager.imagePath = str(imagePath)
    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: False)

    selectedPath = mock_image_manager._prepare_image_path_for_mount()

    assert selectedPath == os.path.abspath(str(imagePath))
    assert mock_image_manager._stagedImagePath is None

def test_network_threshold_boundary_auto_stages(mock_image_manager, monkeypatch, tmp_path):
    """Network image at threshold should auto-stage to local temp."""
    imagePath = tmp_path / 'network.img'
    imagePath.write_bytes(b'test')
    absImagePath = os.path.abspath(str(imagePath))
    
    mock_image_manager.imagePath = str(imagePath)

    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, '_is_in_integration_fixtures', lambda path: False)
    monkeypatch.setattr('lib.managers.image.os.path.getsize', lambda path: ImageFileManager.STAGE_THRESHOLD_BYTES)
    
    staged_calls = []
    def mock_stage_image(path, size):
        staged_calls.append((path, size))
        return '/tmp/staged.img'
    
    monkeypatch.setattr(mock_image_manager, '_stage_image_to_temp', mock_stage_image)

    selectedPath = mock_image_manager._prepare_image_path_for_mount()

    assert selectedPath == '/tmp/staged.img'
    assert staged_calls == [(absImagePath, ImageFileManager.STAGE_THRESHOLD_BYTES)]

def test_large_network_image_rejects_when_non_interactive(mock_image_manager, monkeypatch, tmp_path):
    """Large network image should fail in non-interactive mode."""
    imagePath = tmp_path / 'large-network.img'
    imagePath.write_bytes(b'test')
    mock_image_manager.imagePath = str(imagePath)
    
    imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, '_is_in_integration_fixtures', lambda path: False)
    monkeypatch.setattr('lib.managers.image.os.path.getsize', lambda path: imageSize)
    monkeypatch.setattr('lib.managers.image.sys.stdin.isatty', lambda: False)
    monkeypatch.setattr('lib.managers.image.sys.stdout.isatty', lambda: False)

    with pytest.raises(RuntimeError, match='too large for automatic staging'):
        mock_image_manager._prepare_image_path_for_mount()

def test_network_fixture_image_auto_stages_even_if_large(mock_image_manager, monkeypatch, tmp_path):
    """Fixture-path image should auto-stage even above threshold."""
    fixtureDir = tmp_path / 'tests' / 'integration' / 'fixtures'
    fixtureDir.mkdir(parents=True)
    imagePath = fixtureDir / 'fixture.img'
    imagePath.write_bytes(b'test')
    absImagePath = os.path.abspath(str(imagePath))
    imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1024

    mock_image_manager.imagePath = str(imagePath)
    
    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, '_is_in_integration_fixtures', lambda path: True)
    monkeypatch.setattr('lib.managers.image.os.path.getsize', lambda path: imageSize)
    monkeypatch.setattr(mock_image_manager, '_stage_image_to_temp', lambda p, s: '/tmp/fixture-staged.img')

    selectedPath = mock_image_manager._prepare_image_path_for_mount()

    assert selectedPath == '/tmp/fixture-staged.img'

def test_large_network_image_interactive_yes_stages(mock_image_manager, monkeypatch, tmp_path):
    """Large network image should stage when user confirms in interactive mode."""
    imagePath = tmp_path / 'large-yes.img'
    imagePath.write_bytes(b'test')
    absImagePath = os.path.abspath(str(imagePath))
    imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

    mock_image_manager.imagePath = str(imagePath)

    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, '_is_in_integration_fixtures', lambda path: False)
    monkeypatch.setattr('lib.managers.image.os.path.getsize', lambda path: imageSize)
    monkeypatch.setattr(mock_image_manager, '_get_available_memory_bytes', lambda: 8 * 1024 * 1024 * 1024)
    monkeypatch.setattr(mock_image_manager, '_get_tmp_available_bytes', lambda: 20 * 1024 * 1024 * 1024)
    monkeypatch.setattr(mock_image_manager, '_confirm_stage_large_image', lambda s, n, y: True)
    monkeypatch.setattr(mock_image_manager, '_stage_image_to_temp', lambda p, s: '/tmp/large-yes-staged.img')

    selectedPath = mock_image_manager._prepare_image_path_for_mount()
    assert selectedPath == '/tmp/large-yes-staged.img'

def test_cleanup_staged_image_removes_file(mock_image_manager, tmp_path):
    """Cleanup should remove staged image file and clear state."""
    stagedPath = tmp_path / 'staged.img'
    stagedPath.write_bytes(b'staged')

    mock_image_manager._stagedImagePath = str(stagedPath)
    mock_image_manager._cleanup_staged_image()

    assert mock_image_manager._stagedImagePath is None
    assert not stagedPath.exists()

def test_perform_unmount_delegates_and_cleans_staged_image(mock_image_manager, monkeypatch):
    """Image unmount should delegate to script and always cleanup staged copy."""
    unmount_called = []
    monkeypatch.setattr(mock_image_manager, '_run_unmount_script', lambda forceUnmount: unmount_called.append(True))
    
    cleanup_called = []
    monkeypatch.setattr(mock_image_manager, '_cleanup_staged_image', lambda: cleanup_called.append(True))

    mock_image_manager._perform_unmount(forceUnmount=True)

    assert unmount_called
    assert cleanup_called


# --- Loop Detection Tests ---

def test_loop_device_found(mock_image_manager, monkeypatch):
    """Detect existing loop device for image file."""
    imagePath = "/home/user/test.img"
    mock_image_manager.imagePath = imagePath

    mockLosetup = "/dev/loop0: []: (/home/user/test.img)\n"
    mockMounts = "/dev/loop0p1 /tmp/test/boot vfat rw 0 0\n/dev/loop0p2 /tmp/test ext4 rw 0 0\n"

    monkeypatch.setattr(mock_image_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockLosetup, '', 0))
    monkeypatch.setattr('lib.managers.image.os.path.exists', lambda p: True)
    monkeypatch.setattr('lib.managers.image.os.path.isfile', lambda p: True)
    
    mock_stat = type('obj', (object,), {'st_mode': stat.S_IFREG})
    monkeypatch.setattr('lib.managers.image.os.stat', lambda p, *args, **kwargs: mock_stat)
    
    monkeypatch.setattr('builtins.open', lambda *args, **kwargs: type('obj', (object,), {
        '__enter__': lambda s: mockMounts.splitlines(),
        '__exit__': lambda *args: None
    })())

    mountPath = mock_image_manager._find_existing_loop_mount()
    assert mountPath == "/tmp/test"

def test_no_loop_device(mock_image_manager, monkeypatch):
    """No existing loop device for image file."""
    imagePath = "/home/user/test.img"
    mock_image_manager.imagePath = imagePath

    monkeypatch.setattr(mock_image_manager, 'run_local', lambda cmd, sudo=False: CommandResult('', '', 0))
    monkeypatch.setattr('lib.managers.image.os.path.exists', lambda p: True)
    monkeypatch.setattr('lib.managers.image.os.path.isfile', lambda p: True)
    
    mock_stat = type('obj', (object,), {'st_mode': stat.S_IFREG})
    monkeypatch.setattr('lib.managers.image.os.stat', lambda p, *args, **kwargs: mock_stat)

    result = mock_image_manager._find_existing_loop_mount()
    assert result is None


def test_large_network_image_interactive_no_raises(mock_image_manager, monkeypatch, tmp_path):
    """Large network image should fail when user declines staging."""
    imagePath = tmp_path / 'large-no.img'
    imagePath.write_bytes(b'test')
    
    mock_image_manager.imagePath = str(imagePath)
    imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

    monkeypatch.setattr(mock_image_manager, '_is_network_mounted_path', lambda path: True)
    monkeypatch.setattr(mock_image_manager, '_is_in_integration_fixtures', lambda path: False)
    monkeypatch.setattr('lib.managers.image.os.path.getsize', lambda path: imageSize)
    monkeypatch.setattr(mock_image_manager, '_get_available_memory_bytes', lambda: 8 * 1024 * 1024 * 1024)
    monkeypatch.setattr(mock_image_manager, '_get_tmp_available_bytes', lambda: 20 * 1024 * 1024 * 1024)
    monkeypatch.setattr(mock_image_manager, '_confirm_stage_large_image', lambda s, n, y: False)

    with pytest.raises(RuntimeError, match='too large for automatic staging'):
        mock_image_manager._prepare_image_path_for_mount()

def test_close_cleans_staged_image_on_exit(mock_image_manager, monkeypatch):
    """Manager close should always cleanup staged image copy."""
    cleanup_called = []
    monkeypatch.setattr(mock_image_manager, '_cleanup_staged_image', lambda: cleanup_called.append(True))
    
    # Needs to bypass the super().close() which might crash in mock env
    monkeypatch.setattr('lib.managers.image.BaseImageManager.close', lambda self: None)

    mock_image_manager.close()
    assert cleanup_called
