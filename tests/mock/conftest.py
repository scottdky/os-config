import os
import shutil
import pytest
from lib.managers.base import BaseManager, CommandResult

class MockManager(BaseManager):
    """A MockManager that redirects all filesystem operations to a local tmp_path."""
    def __init__(self, tmp_path):
        super().__init__()
        self.tmp_path = str(tmp_path)
        self.run_history = []
        self.mock_run_results = {} # map command -> CommandResult
        self.sudo_history = []

    def _resolve_path(self, remotePath: str) -> str:
        # Strip leading slash and join with tmp_path
        if remotePath.startswith("/"):
            remotePath = remotePath[1:]
        return os.path.join(self.tmp_path, remotePath)

    def exists(self, remotePath: str) -> bool:
        return os.path.exists(self._resolve_path(remotePath))

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        dest = self._resolve_path(remotePath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(localPath, dest)

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        src = self._resolve_path(remotePath)
        shutil.copy2(src, localPath)

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        self.run_history.append((command, sudo))
        if sudo:
            self.sudo_history.append(command)

        # Cat fallback since base manager uses `run('cat ...')` for read_file
        if command.startswith("cat "):
            filepath = command[4:].strip()
            if self.exists(filepath):
                with open(self._resolve_path(filepath), 'r') as f:
                    return CommandResult(f.read(), "", 0)
            return CommandResult("", "File not found", 1)

        # Allow user to mock specific commands
        if command in self.mock_run_results:
            return self.mock_run_results[command]

        # By default, assume command succeeds
        return CommandResult("Mocked output", "", 0)

    # Added so we don't accidentally do bad host side ops
    def validate_sudo(self, allowInteractiveSudo=None):
        return CommandResult("", "", 0)

    from contextlib import contextmanager
    @contextmanager
    def temporarily_unmounted(self):
        yield

@pytest.fixture
def mock_manager(tmp_path):
    # Setup some basic expected mock directories that most tools assume
    os.makedirs(os.path.join(tmp_path, "etc"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "boot/firmware"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "usr/bin"), exist_ok=True)

    manager = MockManager(tmp_path)

    # Pre-populate raspi-config trigger
    with open(os.path.join(tmp_path, "usr/bin/raspi-config"), "w") as f:
        f.write("# Dummy raspi-config for is_raspi_os")
    os.chmod(os.path.join(tmp_path, "usr/bin/raspi-config"), 0o755)

    return manager
