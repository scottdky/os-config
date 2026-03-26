import pytest
from core.packages import AptPackagesOperation, PipPackagesOperation
from lib.managers.base import CommandResult

def test_apt_packages_operation(mock_manager):
    installed_pkgs = set()
    original_run = mock_manager.run
    def mock_run(command, sudo=False):
        if command.startswith("dpkg-query -W -f='${Status}'"):
            pkg = command.split()[-2].strip("'")
            if pkg in installed_pkgs:
                return CommandResult("install ok installed", "", 0)
            return CommandResult("", "", 0)
        if "apt-get install" in command:
            pkg = command.split()[-1]
            installed_pkgs.add(pkg)
            return CommandResult("", "", 0)
        return original_run(command, sudo)
    mock_manager.run = mock_run

    op = AptPackagesOperation()

    # First install
    record = op.apply(mock_manager, {"apt": ["vim", "curl"]})
    assert record.changed is True
    assert "vim" in installed_pkgs
    assert "curl" in installed_pkgs

    # Second should be idempotency
    record2 = op.apply(mock_manager, {"apt": ["vim", "curl"]})
    assert record2.changed is False

def test_pip_packages_operation(mock_manager):
    # Pip is strictly blind right now
    op = PipPackagesOperation()
    record = op.apply(mock_manager, {"pip": ["pytest", "requests"]})
    assert record.changed is True

    # No true idempotency in current code if the pip command runs every time
    # Check that the PIP commands ran
    run_pytest = any(cmd for cmd, _ in mock_manager.run_history if 'pip3 install pytest' in cmd)
    run_requests = any(cmd for cmd, _ in mock_manager.run_history if 'pip3 install requests' in cmd)
    assert run_pytest
    assert run_requests
