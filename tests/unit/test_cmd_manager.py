import os
import sys
import pytest

# Add project root to sys.path so we can import lib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.cmd_manager import LocalManager, BaseImageManager, ImageFileManager, SDCardManager, DEFAULT_MOUNT_PATH

pytestmark = pytest.mark.unit


@pytest.fixture
def local_manager(tmp_path):
    """Fixture to provide a LocalManager instance working in a temporary directory."""
    manager = LocalManager()
    yield manager, tmp_path
    manager.close()


def test_run_simple_command(local_manager):
    """Test 'run': Verify simple command execution."""
    manager, _ = local_manager
    stdout, stderr, code = manager.run("echo 'hello world'")
    assert code == 0
    assert "hello world" in stdout.strip()
    assert stderr == ""


def test_put_file(local_manager):
    """Test 'put': Verify file copying."""
    manager, tmp_path = local_manager
    source_file = tmp_path / "source.txt"
    dest_file = tmp_path / "dest.txt"

    source_content = "some content"
    source_file.write_text(source_content)

    manager.put(str(source_file), str(dest_file))

    assert dest_file.exists()
    assert dest_file.read_text() == source_content


def test_exists(local_manager):
    """Test 'exists': Verify file existence checks."""
    manager, tmp_path = local_manager
    test_file = tmp_path / "test_exists.txt"

    assert not manager.exists(str(test_file))

    test_file.touch()
    assert manager.exists(str(test_file))


def test_append_new_lines_list(local_manager):
    """Test 'append': Append new lines (list inputs)."""
    manager, tmp_path = local_manager
    target_file = tmp_path / "config.txt"
    initial_content = "line1\nline2\n"
    target_file.write_text(initial_content)

    lines_to_append = ["line3", "line4"]
    manager.append(str(target_file), lines_to_append)

    expected_content = "line1\nline2\nline3\nline4\n"
    assert target_file.read_text() == expected_content


def test_append_ignores_existing_lines(local_manager):
    """Test 'append': Append ignores already existing lines."""
    manager, tmp_path = local_manager
    target_file = tmp_path / "config.txt"
    initial_content = "line1\nline2\n"
    target_file.write_text(initial_content)

    manager.append(str(target_file), ["line1", "line3"])

    expected_content = "line1\nline2\nline3\n"
    assert target_file.read_text() == expected_content


def test_append_uncomment_logic(local_manager):
    """Test 'append': Verify that commented lines are uncommented."""
    manager, tmp_path = local_manager
    target_file = tmp_path / "config.txt"

    target_file.write_text("# my_config=true\nother=value\n")
    manager.append(str(target_file), "my_config=true")
    assert target_file.read_text() == "my_config=true\nother=value\n"

    target_file.write_text("#my_config=true\n")
    manager.append(str(target_file), "my_config=true")
    assert target_file.read_text() == "my_config=true\n"

    target_file.write_text("    # my_config=true\n")
    manager.append(str(target_file), "my_config=true")
    assert target_file.read_text() == "my_config=true\n"


def test_append_creates_file_if_missing(local_manager):
    """Test 'append': Verify it handles non-existent files (should append to empty)."""
    manager, tmp_path = local_manager
    target_file = tmp_path / "new_config.txt"

    manager.append(str(target_file), "line1")

    assert target_file.exists()
    assert target_file.read_text() == "line1\n"


def test_default_mount_path_constant_used_everywhere():
    """Mount defaults should be centralized through DEFAULT_MOUNT_PATH."""
    assert BaseImageManager.__init__.__defaults__[0] == DEFAULT_MOUNT_PATH
    assert ImageFileManager.__init__.__defaults__[0] == DEFAULT_MOUNT_PATH
    assert SDCardManager.__init__.__defaults__[0] == DEFAULT_MOUNT_PATH
    assert SDCardManager.from_interactive_selection.__defaults__[0] == DEFAULT_MOUNT_PATH


def test_base_image_close_skips_unmount_when_keep_mounted_true():
    """keepMounted=True should skip unmount on close."""
    manager = BaseImageManager.__new__(BaseImageManager)
    manager.mountPath = DEFAULT_MOUNT_PATH
    manager.keepMounted = True
    manager._mountedByUs = {'root': True}

    unmountCalled = {'value': False}

    def fake_unmount():
        unmountCalled['value'] = True

    manager._unmount = fake_unmount
    manager.close()

    assert unmountCalled['value'] is False


def test_base_image_close_unmounts_when_mount_active_even_if_not_tracked():
    """Default close should unmount when mount target is active even if _mountedByUs is falsey."""
    manager = BaseImageManager.__new__(BaseImageManager)
    manager.mountPath = DEFAULT_MOUNT_PATH
    manager.keepMounted = False
    manager._mountedByUs = {'root': False}

    unmountCalled = {'value': False}

    def fake_unmount():
        unmountCalled['value'] = True

    manager._unmount = fake_unmount
    manager._is_mount_active = lambda: True
    manager.close()

    assert unmountCalled['value'] is True
