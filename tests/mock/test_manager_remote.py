import pytest
from lib.managers.remote import SSHManager
from lib.managers.base import CommandResult
import paramiko

@pytest.fixture
def ssh_manager(monkeypatch):
    monkeypatch.setattr('lib.managers.base.BaseManager.validate_sudo', lambda self: CommandResult("", "", 0))
    class MockSSHClient:
        def __init__(self):
            self.closed = False
            self.connect_calls = []
            self.sftp_closed = False

            def mock_sftp_close(s):
                self.sftp_closed = True

            self.sftp_mock = type('obj', (), {'put': lambda self, s, d: None, 'get': lambda self, s, d: None, 'close': mock_sftp_close})()

        def set_missing_host_key_policy(self, policy):
            pass
        def connect(self, **kwargs):
            self.connect_calls.append(kwargs)
        def close(self):
            self.closed = True
        def open_sftp(self):
            return self.sftp_mock
        def exec_command(self, cmd):
            stdout = type('obj', (), {'channel': type('obj', (), {'recv_exit_status': lambda *args: 0})(), 'read': lambda *args, **kwargs: b"out"})()
            stderr = type('obj', (), {'read': lambda *args, **kwargs: b"err"})()
            return (None, stdout, stderr)

    monkeypatch.setattr(paramiko, 'SSHClient', MockSSHClient)

    mgr = SSHManager(hostName="dummy", userName="pi")
    return mgr

def test_ssh_manager_connect(ssh_manager, monkeypatch):
    with ssh_manager as m:
        assert m.client.connect_calls
        assert m.sftp is not None
        mock_client = m.client
    assert mock_client.closed
    assert mock_client.sftp_closed

def test_ssh_manager_run(ssh_manager, monkeypatch):
    calls = []
    original_exec = ssh_manager.client.exec_command
    def mock_exec_command(cmd):
        calls.append(cmd)
        return original_exec(cmd)

    monkeypatch.setattr(ssh_manager.client, 'exec_command', mock_exec_command)

    result = ssh_manager.run("echo hello")
    assert result.returnCode == 0
    assert result.stdout == "out"
    assert result.stderr == "err"

    assert len(calls) == 1
    assert "echo hello" in calls[0]

def test_ssh_manager_put_get(ssh_manager, monkeypatch):
    mock_sftp = type('obj', (), {'put_calls': [], 'get_calls': [], 'put': lambda self, s, d: self.put_calls.append((s, d)), 'get': lambda self, s, d: self.get_calls.append((s, d))})()
    ssh_manager.sftp = mock_sftp

    monkeypatch.setattr(ssh_manager, 'run', lambda cmd, sudo=False: CommandResult("","",0))

    ssh_manager.put('/src', '/dst')
    assert ('/src', '/dst') in mock_sftp.put_calls

    ssh_manager.get('/src', '/dst')
    assert ('/src', '/dst') in mock_sftp.get_calls

def test_ssh_manager_write_file(ssh_manager, monkeypatch):
    calls = []
    monkeypatch.setattr(ssh_manager, 'run', lambda cmd, sudo=False: calls.append((cmd, sudo)) or CommandResult("","",0))

    ssh_manager.sftp = type('obj', (), {'put': lambda self, s, d: None})()
    ssh_manager.write_file('/path', 'content', sudo=True)
    assert any('mv /tmp/path /path' in cmd and sudo for cmd, sudo in calls)
