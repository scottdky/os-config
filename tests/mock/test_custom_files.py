import pytest
import os
from core.custom_files import CustomFilesOperation

def test_custom_files_no_files(mock_manager):
    op = CustomFilesOperation()
    record = op.apply(mock_manager, {"files": []})
    assert record.changed is False

def test_custom_files_create_new(mock_manager, tmp_path):
    # Setup some source file
    source_path = os.path.join(tmp_path, "local_source.txt")
    with open(source_path, "w") as f:
        f.write("local content")

    op = CustomFilesOperation()
    configs = {
        "files": [
            {
                "target": "/etc/custom1.txt",
                "content": "direct content\n"
            },
            {
                "target": "/etc/custom2.txt",
                "local_source": source_path
            }
        ]
    }

    # First apply
    record = op.apply(mock_manager, configs)
    assert record.changed is True

    # Verify content
    assert mock_manager.read_file("/etc/custom1.txt") == "direct content\n"
    assert mock_manager.read_file("/etc/custom2.txt") == "local content"

    # Second apply (idempotency)
    record2 = op.apply(mock_manager, configs)
    assert record2.changed is False

def test_custom_files_executable_and_service(mock_manager):
    op = CustomFilesOperation()
    configs = {
        "files": [
            {
                "target": "/usr/local/bin/test_script",
                "content": "#!/bin/sh\necho hi",
                "executable": True,
            },
            {
                "target": "/etc/systemd/system/test_service.service",
                "content": "[Unit]\nDescription=Test",
                "enable_service": True
            }
        ]
    }
    record = op.apply(mock_manager, configs)
    assert record.changed is True

    # Check that commands were run to chmod and systemd enable
    chmod_run = any(cmd for cmd, _ in mock_manager.run_history if "chmod +x" in cmd and "/usr/local/bin/test_script" in cmd)
    assert chmod_run

    enable_run = any(cmd for cmd, _ in mock_manager.run_history if "systemctl enable" in cmd and "test_service" in cmd)
    assert enable_run
