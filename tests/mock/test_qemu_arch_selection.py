"""Mock tests for architecture-based QEMU selection."""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.cmd_manager import BaseImageManager


class _DummyImageManager(BaseImageManager):
    """Minimal concrete subclass for method-level tests."""

    def _validate_target(self) -> None:
        return

    def _perform_mount(self) -> None:
        return


@pytest.mark.mock
class TestQemuArchSelection:
    """Test architecture detection and QEMU binary selection."""

    @staticmethod
    def _create_manager() -> _DummyImageManager:
        manager = _DummyImageManager.__new__(_DummyImageManager)
        manager.mountPath = '/tmp/os_image'
        manager._qemuStaticBinary = 'qemu-arm-static'
        return manager

    def test_detect_qemu_binary_aarch64(self):
        """AArch64 ELF should select qemu-aarch64-static."""
        manager = self._create_manager()

        with mock.patch.object(manager, '_run_local', return_value=(
            '  Machine:                           AArch64\n', '', 0
        )):
            binary = manager._detect_qemu_static_binary()

        assert binary == 'qemu-aarch64-static'

    def test_detect_qemu_binary_arm(self):
        """ARM ELF should select qemu-arm-static."""
        manager = self._create_manager()

        with mock.patch.object(manager, '_run_local', return_value=(
            '  Machine:                           ARM\n', '', 0
        )):
            binary = manager._detect_qemu_static_binary()

        assert binary == 'qemu-arm-static'

    def test_detect_qemu_binary_fallback_on_error(self):
        """Detection failure should fallback to qemu-arm-static."""
        manager = self._create_manager()

        with mock.patch.object(manager, '_run_local', return_value=('', 'readelf failed', 1)):
            binary = manager._detect_qemu_static_binary()

        assert binary == 'qemu-arm-static'

    def test_run_uses_selected_qemu_binary(self):
        """run() should execute chroot with the selected QEMU binary path."""
        manager = self._create_manager()
        manager.defaultChrootUser = None

        capturedCommand = {'value': ''}

        def fake_run_local(command: str, sudo: bool = False, allowInteractiveSudo=None):
            capturedCommand['value'] = command
            return '', '', 0

        with mock.patch.object(manager, '_run_local', side_effect=fake_run_local):
            manager.run('echo ok', sudo=True)

        assert '/usr/bin/qemu-arm-static' in capturedCommand['value']
