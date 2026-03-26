import pytest
import subprocess
import shutil
import os
from lib.managers.local import LocalManager
from lib.managers.base import CommandResult

@pytest.fixture
def local_manager():
    return LocalManager()

def test_local_manager_run(local_manager, monkeypatch):
    calls = []

    def mock_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return type('CompletedProcess', (), {'returncode': 0, 'stdout': "out", 'stderr': "err"})()

    monkeypatch.setattr(subprocess, 'run', mock_subprocess_run)

    result = local_manager.run("echo hello")
    assert result.returnCode == 0
    assert result.stdout == "out"
    assert result.stderr == "err"

    assert len(calls) == 1
    args, kwargs = calls[0]
    # Local manager is essentially doing shlex.split("echo hello")
    cmd_str = args if isinstance(args, str) else " ".join(args)
    assert "echo hello" in cmd_str

def test_local_manager_run_sudo(local_manager, monkeypatch):
    calls = []

    def mock_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return type('CompletedProcess', (), {'returncode': 0, 'stdout': "out", 'stderr': "err"})()

    monkeypatch.setattr(subprocess, 'run', mock_subprocess_run)
    monkeypatch.setattr('lib.managers.base.BaseManager.validate_sudo', lambda self, **kwargs: CommandResult("","",0))

    result = local_manager.run("echo hello", sudo=True)
    assert result.returnCode == 0

    assert len(calls) == 1
    args, kwargs = calls[0]
    cmd_str = args if isinstance(args, str) else " ".join(args)
    assert "sudo" in cmd_str

def test_local_manager_put_get(local_manager, monkeypatch):
    calls = []

    def mock_shutil_copy(src, dst):
        calls.append(('copy', src, dst))

    def mock_run(cmd, sudo=False, **kwargs):
        calls.append(('run', cmd, sudo))
        return CommandResult("", "", 0)

    monkeypatch.setattr(shutil, 'copy2', mock_shutil_copy)
    monkeypatch.setattr(local_manager, 'run', mock_run)
    monkeypatch.setattr(local_manager, 'run_local', mock_run)

    local_manager.put('/src', '/dst')
    assert ('copy', '/src', '/dst') in calls

    calls.clear()
    local_manager.get('/src', '/dst', sudo=True)
    assert ('run', 'cp /src /dst', True) in calls

def test_local_manager_read_write(local_manager, monkeypatch):
    class MockFile:
        def read(self): return "content"
        def write(self, data): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr('builtins.open', lambda *args, **kwargs: MockFile())
    monkeypatch.setattr('lib.managers.local.os.path.exists', lambda p: True)

    monkeypatch.setattr(local_manager, 'run_local', lambda cmd, **kwargs: CommandResult('content', '', 0))
    assert local_manager.read_file('/path/to/file') == 'content'

    write_calls = []
    def mock_run(cmd, sudo=False, **kwargs):
        write_calls.append((cmd, sudo))
        return CommandResult("", "", 0)

    monkeypatch.setattr(local_manager, 'run', mock_run)
    monkeypatch.setattr(local_manager, 'run_local', mock_run)
    local_manager.write_file('/path/to/file', 'new content', sudo=True)

    assert any('cp ' in cmd and '/path/to/file' in cmd and sudo for cmd, sudo in write_calls)


