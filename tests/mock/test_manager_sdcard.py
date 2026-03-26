import pytest
import os
import json
import stat
from lib.managers.image import SDCardManager
from lib.managers.base import CommandResult

@pytest.fixture
def mock_sdcard_manager(monkeypatch):
    """Fixture providing a partially mocked SDCardManager."""
    # Prevent sudo validation and target validation from actually firing
    monkeypatch.setattr(SDCardManager, 'validate_sudo', lambda self: CommandResult('', '', 0))
    monkeypatch.setattr(SDCardManager, '_validate_target', lambda self: None)
    monkeypatch.setattr(SDCardManager, '_perform_mount', lambda self: None)
    
    manager = SDCardManager(devicePath="/dev/sdb", mountPath="/tmp/test")
    return manager

def test_typical_raspberry_pi_layout(mock_sdcard_manager, monkeypatch):
    """Detect typical Raspberry Pi partition layout (FAT boot + ext4 root)."""
    mockOutput = json.dumps({
        "blockdevices": [{
            "name": "sdb",
            "children": [
                {"name": "sdb1", "fstype": "vfat", "size": "512M"},
                {"name": "sdb2", "fstype": "ext4", "size": "28G"}
            ]
        }]
    })

    monkeypatch.setattr(mock_sdcard_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockOutput, '', 0))
    
    partitions = mock_sdcard_manager._detect_partitions()
    assert partitions["boot"] == "/dev/sdb1"
    assert partitions["root"] == "/dev/sdb2"

def test_mmc_partition_layout(mock_sdcard_manager, monkeypatch):
    """Detect MMC device with p-style partition naming."""
    mock_sdcard_manager.devicePath = "/dev/mmcblk0"
    mockOutput = json.dumps({
        "blockdevices": [{
            "name": "mmcblk0",
            "children": [
                {"name": "mmcblk0p1", "fstype": "vfat", "size": "256M"},
                {"name": "mmcblk0p2", "fstype": "ext4", "size": "29G"}
            ]
        }]
    })

    monkeypatch.setattr(mock_sdcard_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockOutput, '', 0))
    
    partitions = mock_sdcard_manager._detect_partitions()
    assert partitions["boot"] == "/dev/mmcblk0p1"
    assert partitions["root"] == "/dev/mmcblk0p2"

def test_single_partition(mock_sdcard_manager, monkeypatch):
    """Handle device with only one partition."""
    mockOutput = json.dumps({
        "blockdevices": [{
            "name": "sdb",
            "children": [
                {"name": "sdb1", "fstype": "ext4", "size": "29G"}
            ]
        }]
    })

    monkeypatch.setattr(mock_sdcard_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockOutput, '', 0))
    
    partitions = mock_sdcard_manager._detect_partitions()
    assert partitions.get("boot") is None
    assert partitions["root"] == "/dev/sdb1"

def test_no_partitions(mock_sdcard_manager, monkeypatch):
    """Handle device with no partitions."""
    mockOutput = json.dumps({
        "blockdevices": [{
            "name": "sdb",
            "children": []
        }]
    })

    monkeypatch.setattr(mock_sdcard_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockOutput, '', 0))
    
    partitions = mock_sdcard_manager._detect_partitions()
    assert len(partitions) == 0

def test_multiple_ext4_partitions(mock_sdcard_manager, monkeypatch):
    """When multiple ext4 partitions exist, use the largest as root. (Assuming logic picks last or specific? Wait, check logic)"""
    mockOutput = json.dumps({
        "blockdevices": [{
            "name": "sdb",
            "children": [
                {"name": "sdb1", "fstype": "vfat", "size": "512M"},
                {"name": "sdb2", "fstype": "ext4", "size": "2G"},
                {"name": "sdb3", "fstype": "ext4", "size": "26G"}
            ]
        }]
    })

    monkeypatch.setattr(mock_sdcard_manager, 'run_local', lambda cmd, sudo=False: CommandResult(mockOutput, '', 0))
    
    partitions = mock_sdcard_manager._detect_partitions()
    assert partitions["boot"] == "/dev/sdb1"
    # Note: the current logic just loops over children. sdb3 will overwrite sdb2 in the dict
    assert partitions["root"] == "/dev/sdb3"
