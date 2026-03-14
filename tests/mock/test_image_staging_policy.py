"""Mock tests for network image staging policy.

Tests ImageFileManager staging decisions for local vs network paths,
threshold handling, and non-interactive large-image behavior.
"""

import os
import pytest
from unittest import mock

import sys

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.managers import ImageFileManager


@pytest.mark.mock
class TestImageStagingPolicy:
    """Test image staging decision logic with mocked dependencies."""

    @staticmethod
    def _create_manager(imagePath: str) -> ImageFileManager:
        """Create ImageFileManager instance without running full __init__."""
        manager = ImageFileManager.__new__(ImageFileManager)
        manager.imagePath = imagePath
        manager._stagedImagePath = None
        return manager

    def test_local_path_skips_staging(self, tmp_path):
        """Local filesystem image path should mount directly without staging."""
        imagePath = tmp_path / 'local.img'
        imagePath.write_bytes(b'test')

        manager = self._create_manager(str(imagePath))

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=False):
            selectedPath = manager._prepare_image_path_for_mount()

        assert selectedPath == os.path.abspath(str(imagePath))
        assert manager._stagedImagePath is None

    def test_network_threshold_boundary_auto_stages(self, tmp_path):
        """Network image at threshold should auto-stage to local temp."""
        imagePath = tmp_path / 'network.img'
        imagePath.write_bytes(b'test')
        absImagePath = os.path.abspath(str(imagePath))

        manager = self._create_manager(str(imagePath))

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=True), \
             mock.patch.object(manager, '_is_in_integration_fixtures', return_value=False), \
             mock.patch('lib.managers.image.os.path.getsize', return_value=ImageFileManager.STAGE_THRESHOLD_BYTES), \
             mock.patch.object(manager, '_stage_image_to_temp', return_value='/tmp/staged.img') as stageMock:
            selectedPath = manager._prepare_image_path_for_mount()

        assert selectedPath == '/tmp/staged.img'
        stageMock.assert_called_once_with(absImagePath, ImageFileManager.STAGE_THRESHOLD_BYTES)

    def test_large_network_image_rejects_when_non_interactive(self, tmp_path):
        """Large network image should fail in non-interactive mode."""
        imagePath = tmp_path / 'large-network.img'
        imagePath.write_bytes(b'test')

        manager = self._create_manager(str(imagePath))
        imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=True), \
             mock.patch.object(manager, '_is_in_integration_fixtures', return_value=False), \
             mock.patch('lib.managers.image.os.path.getsize', return_value=imageSize), \
             mock.patch('lib.managers.image.sys.stdin.isatty', return_value=False), \
             mock.patch('lib.managers.image.sys.stdout.isatty', return_value=False):
            with pytest.raises(RuntimeError, match='too large for automatic staging'):
                manager._prepare_image_path_for_mount()

    def test_network_fixture_image_auto_stages_even_if_large(self, tmp_path):
        """Fixture-path image should auto-stage even above threshold."""
        fixtureDir = tmp_path / 'tests' / 'integration' / 'fixtures'
        fixtureDir.mkdir(parents=True)
        imagePath = fixtureDir / 'fixture.img'
        imagePath.write_bytes(b'test')
        absImagePath = os.path.abspath(str(imagePath))
        imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1024

        manager = self._create_manager(str(imagePath))

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=True), \
             mock.patch.object(manager, '_is_in_integration_fixtures', return_value=True), \
             mock.patch('lib.managers.image.os.path.getsize', return_value=imageSize), \
             mock.patch.object(manager, '_stage_image_to_temp', return_value='/tmp/fixture-staged.img') as stageMock:
            selectedPath = manager._prepare_image_path_for_mount()

        assert selectedPath == '/tmp/fixture-staged.img'
        stageMock.assert_called_once_with(absImagePath, imageSize)

    def test_large_network_image_interactive_yes_stages(self, tmp_path):
        """Large network image should stage when user confirms in interactive mode."""
        imagePath = tmp_path / 'large-yes.img'
        imagePath.write_bytes(b'test')
        absImagePath = os.path.abspath(str(imagePath))
        imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

        manager = self._create_manager(str(imagePath))

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=True), \
             mock.patch.object(manager, '_is_in_integration_fixtures', return_value=False), \
             mock.patch('lib.managers.image.os.path.getsize', return_value=imageSize), \
             mock.patch.object(manager, '_get_available_memory_bytes', return_value=8 * 1024 * 1024 * 1024), \
             mock.patch.object(manager, '_get_tmp_available_bytes', return_value=20 * 1024 * 1024 * 1024), \
             mock.patch.object(manager, '_confirm_stage_large_image', return_value=True), \
             mock.patch.object(manager, '_stage_image_to_temp', return_value='/tmp/large-yes-staged.img') as stageMock:
            selectedPath = manager._prepare_image_path_for_mount()

        assert selectedPath == '/tmp/large-yes-staged.img'
        stageMock.assert_called_once_with(absImagePath, imageSize)

    def test_large_network_image_interactive_no_raises(self, tmp_path):
        """Large network image should fail when user declines staging."""
        imagePath = tmp_path / 'large-no.img'
        imagePath.write_bytes(b'test')
        imageSize = ImageFileManager.STAGE_THRESHOLD_BYTES + 1

        manager = self._create_manager(str(imagePath))

        with mock.patch.object(manager, '_is_network_mounted_path', return_value=True), \
             mock.patch.object(manager, '_is_in_integration_fixtures', return_value=False), \
             mock.patch('lib.managers.image.os.path.getsize', return_value=imageSize), \
             mock.patch.object(manager, '_get_available_memory_bytes', return_value=8 * 1024 * 1024 * 1024), \
             mock.patch.object(manager, '_get_tmp_available_bytes', return_value=20 * 1024 * 1024 * 1024), \
             mock.patch.object(manager, '_confirm_stage_large_image', return_value=False):
            with pytest.raises(RuntimeError, match='too large for automatic staging'):
                manager._prepare_image_path_for_mount()

    def test_cleanup_staged_image_removes_file(self, tmp_path):
        """Cleanup should remove staged image file and clear state."""
        stagedPath = tmp_path / 'staged.img'
        stagedPath.write_bytes(b'staged')

        manager = self._create_manager('/tmp/source.img')
        manager._stagedImagePath = str(stagedPath)

        manager._cleanup_staged_image()

        assert manager._stagedImagePath is None
        assert not stagedPath.exists()

    def test_cleanup_staged_image_noop_without_file(self):
        """Cleanup should be no-op when no staged image exists."""
        manager = self._create_manager('/tmp/source.img')
        manager._stagedImagePath = None

        manager._cleanup_staged_image()

        assert manager._stagedImagePath is None

    def test_perform_unmount_delegates_and_cleans_staged_image(self):
        """Image unmount should delegate to script and always cleanup staged copy."""
        manager = self._create_manager('/tmp/source.img')

        with mock.patch.object(manager, '_run_unmount_script') as unmountMock, \
             mock.patch.object(manager, '_cleanup_staged_image') as cleanupMock:
            manager._perform_unmount(forceUnmount=True)

        unmountMock.assert_called_once_with(forceUnmount=True)
        cleanupMock.assert_called_once()

    def test_close_cleans_staged_image_on_exit(self):
        """Manager close should always cleanup staged image copy."""
        manager = self._create_manager('/tmp/source.img')

        with mock.patch('lib.managers.image.BaseImageManager.close') as baseCloseMock, \
             mock.patch.object(manager, '_cleanup_staged_image') as cleanupMock:
            manager.close()

        baseCloseMock.assert_called_once()
        cleanupMock.assert_called_once()

    def test_close_cleans_staged_image_when_base_close_fails(self):
        """Manager close should cleanup staged image even if base close raises."""
        manager = self._create_manager('/tmp/source.img')

        with mock.patch('lib.managers.image.BaseImageManager.close', side_effect=RuntimeError('close failed')), \
             mock.patch.object(manager, '_cleanup_staged_image') as cleanupMock:
            with pytest.raises(RuntimeError, match='close failed'):
                manager.close()

        cleanupMock.assert_called_once()
