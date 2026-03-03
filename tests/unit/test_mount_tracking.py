"""Unit tests for mount tracking logic.

Tests the _mountedByUs dictionary that tracks which mounts
were created by the manager vs pre-existing.
"""
import pytest
from unittest import mock
import sys
import os

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from lib.cmd_manager import SDCardManager


@pytest.mark.unit
class TestMountTracking:
    """Test _mountedByUs tracking dictionary operations."""

    def _create_manager(self) -> SDCardManager:
        """Create manager instance without touching real devices or mounts."""
        with mock.patch.object(SDCardManager, '_validate_target'), \
             mock.patch.object(SDCardManager, '_perform_mount'):
            return SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test")

    def test_initial_state_empty(self):
        """New manager should have empty mount tracking."""
        mgr = self._create_manager()
        assert len(mgr._mountedByUs) == 0

    def test_track_new_mount(self):
        """Can track a new mount."""
        mgr = self._create_manager()

        # Simulate tracking a mount
        mgr._mountedByUs["/tmp/test/boot"] = True

        assert len(mgr._mountedByUs) == 1
        assert mgr._mountedByUs.get("/tmp/test/boot") is True

    def test_track_preexisting_mount(self):
        """Can mark a mount as pre-existing (not ours)."""
        mgr = self._create_manager()

        # Mark as pre-existing
        mgr._mountedByUs["/tmp/test/boot"] = False

        assert len(mgr._mountedByUs) == 1
        assert mgr._mountedByUs.get("/tmp/test/boot") is False

    def test_multiple_mounts(self):
        """Can track multiple mounts with different states."""
        mgr = self._create_manager()

        # boot partition was already mounted
        mgr._mountedByUs["/tmp/test/boot"] = False

        # root partition we mounted ourselves
        mgr._mountedByUs["/tmp/test"] = True

        assert len(mgr._mountedByUs) == 2
        assert mgr._mountedByUs.get("/tmp/test/boot") is False
        assert mgr._mountedByUs.get("/tmp/test") is True

    def test_check_before_unmount(self):
        """Cleanup logic should only unmount what we mounted."""
        mgr = self._create_manager()

        mgr._mountedByUs["/tmp/test/boot"] = False  # pre-existing
        mgr._mountedByUs["/tmp/test"] = True        # we mounted this

        # Simulate cleanup logic
        pathsToUnmount = [
            path for path, weMounted in mgr._mountedByUs.items()
            if weMounted is True
        ]

        assert len(pathsToUnmount) == 1
        assert pathsToUnmount[0] == "/tmp/test"
