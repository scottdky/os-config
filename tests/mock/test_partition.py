import pytest
from core.partition import PartitionOperation
from lib.managers.base import CommandResult

def test_partition_operation(mock_manager, monkeypatch):
    mock_manager.is_os_image = lambda: True
    mock_manager.imagePath = "/fake/image.img"

    import core.partition as cp
    monkeypatch.setattr(cp, 'expand_image_file', lambda mgr, amt: None)
    monkeypatch.setattr(cp, 'expand_partition', lambda mgr, num, size_mb: None)
    monkeypatch.setattr(cp, 'add_partition', lambda mgr, lbl, size_mb, fs: "/dev/loop99")
    monkeypatch.setattr(cp, 'resolve_partition_num', lambda mgr, p: 2)
    monkeypatch.setattr(cp, 'is_last_partition', lambda mgr, num: True)
    monkeypatch.setattr(cp, 'check_partition_exists', lambda mgr, lbl: False)

    # Empty fstab to start
    mock_manager.write_file('/etc/fstab', '')

    op = PartitionOperation()

    configs = {
        'image_expand_mb': 100,
        'resize_partitions': [
            {'label': 'rootfs', 'size_mb': 200}
        ],
        'add_partitions': [
            {'label': 'data', 'size_mb': 300, 'fs': 'ext4', 'copy_source': ''}
        ]
    }

    record = op.apply(mock_manager, configs)
    assert record.changed is True

    # Verify fstab had the data partition added
    fstab_content = mock_manager.read_file('/etc/fstab')
    assert 'LABEL=data' in fstab_content
    assert '/data' in fstab_content

    # Idempotency relies on check_partition_exists and not doing sizes if already done.
    # We will simulate check_partition_exists = True
    monkeypatch.setattr(cp, 'check_partition_exists', lambda mgr, lbl: True)
    configs['image_expand_mb'] = 0
    configs['resize_partitions'] = []

    record2 = op.apply(mock_manager, configs)
    assert record2.changed is False
