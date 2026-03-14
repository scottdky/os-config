"""Mock tests for integration cleanup safety behavior."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import tests.integration.conftest as integrationConftest


UNMOUNT_SCOPED_TREE = getattr(integrationConftest, '_unmountScopedTree')


@pytest.mark.mock
def test_unmount_scoped_tree_ignores_non_pytest_paths(monkeypatch):
    """Cleanup should ignore paths outside /tmp/pytest_mount_* scope."""

    runCalls: list[list[str]] = []
    monkeypatch.setattr(integrationConftest.subprocess, 'run', lambda *args, **kwargs: runCalls.append(args[0]))

    UNMOUNT_SCOPED_TREE('/mnt/normal-path')

    assert runCalls == []


@pytest.mark.mock
def test_unmount_scoped_tree_skips_when_script_missing(monkeypatch):
    """Cleanup should do nothing when shared unmount script is unavailable."""

    monkeypatch.setattr(integrationConftest, 'UNMOUNT_SCRIPT', '/missing/unmnt_image.sh')
    monkeypatch.setattr(integrationConftest.os.path, 'exists', lambda path: False)

    runCalls: list[list[str]] = []
    monkeypatch.setattr(integrationConftest.subprocess, 'run', lambda *args, **kwargs: runCalls.append(args[0]))

    UNMOUNT_SCOPED_TREE('/tmp/pytest_mount_case')

    assert runCalls == []


@pytest.mark.mock
def test_unmount_scoped_tree_runs_normal_only_when_unmounted(monkeypatch):
    """Cleanup should stop after normal unmount when target is no longer mounted."""

    monkeypatch.setattr(integrationConftest, 'UNMOUNT_SCRIPT', '/fake/unmnt_image.sh')

    def fake_exists(path: str) -> bool:
        if path == '/fake/unmnt_image.sh':
            return True
        return False

    monkeypatch.setattr(integrationConftest.os.path, 'exists', fake_exists)
    monkeypatch.setattr(integrationConftest, '_is_mount_active', lambda path: False)

    runCalls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        runCalls.append(cmd)

        class _Result:
            returncode = 0
            stdout = ''
            stderr = ''

        return _Result()

    monkeypatch.setattr(integrationConftest.subprocess, 'run', fake_run)

    UNMOUNT_SCOPED_TREE('/tmp/pytest_mount_case')

    assert runCalls == [['bash', '/fake/unmnt_image.sh', '/tmp/pytest_mount_case']]


@pytest.mark.mock
def test_unmount_scoped_tree_refuses_force_for_non_owned_mount(monkeypatch):
    """Cleanup must not force unmount when ownership marker is absent."""

    monkeypatch.setattr(integrationConftest, 'UNMOUNT_SCRIPT', '/fake/unmnt_image.sh')

    def fake_exists(path: str) -> bool:
        return path == '/fake/unmnt_image.sh'

    monkeypatch.setattr(integrationConftest.os.path, 'exists', fake_exists)
    monkeypatch.setattr(integrationConftest, '_is_mount_active', lambda path: True)

    runCalls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        runCalls.append(cmd)

        class _Result:
            returncode = 0
            stdout = ''
            stderr = ''

        return _Result()

    monkeypatch.setattr(integrationConftest.subprocess, 'run', fake_run)

    UNMOUNT_SCOPED_TREE('/tmp/pytest_mount_case')

    assert runCalls == [['bash', '/fake/unmnt_image.sh', '/tmp/pytest_mount_case']]


@pytest.mark.mock
def test_unmount_scoped_tree_uses_force_for_owned_mount(monkeypatch):
    """Cleanup should force unmount only when marker confirms test ownership."""

    monkeypatch.setattr(integrationConftest, 'UNMOUNT_SCRIPT', '/fake/unmnt_image.sh')
    ownedMarker = f"/tmp/pytest_mount_case/{integrationConftest.OWNERSHIP_MARKER_NAME}"

    def fake_exists(path: str) -> bool:
        return path in {'/fake/unmnt_image.sh', ownedMarker}

    monkeypatch.setattr(integrationConftest.os.path, 'exists', fake_exists)
    monkeypatch.setattr(integrationConftest, '_is_mount_active', lambda path: True)

    runCalls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        runCalls.append(cmd)

        class _Result:
            returncode = 0
            stdout = ''
            stderr = ''

        return _Result()

    monkeypatch.setattr(integrationConftest.subprocess, 'run', fake_run)

    UNMOUNT_SCOPED_TREE('/tmp/pytest_mount_case')

    assert runCalls == [
        ['bash', '/fake/unmnt_image.sh', '/tmp/pytest_mount_case'],
        ['bash', '/fake/unmnt_image.sh', '/tmp/pytest_mount_case', 'force'],
    ]
