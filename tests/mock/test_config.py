import os
import sys
import pytest
import yaml
from unittest.mock import patch

# Add project root to sys.path so we can import lib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib import config

pytestmark = pytest.mark.mock


@pytest.fixture
def clean_env(tmp_path):
    """Setup a temporary directory structure for config testing."""
    root = tmp_path
    core_dir = root / "core"
    core_dir.mkdir()
    plugins_dir = root / "plugins" / "myplugin"
    plugins_dir.mkdir(parents=True)

    with patch("lib.config._get_project_root", return_value=str(root)):
        yield root


def test_find_config_files(clean_env):
    """Test that config files are found and sorted correctly (deepest first)."""
    root = clean_env

    (root / "config.yaml").touch()
    (root / "core/config.yaml").touch()
    (root / "plugins/myplugin/config.yaml").touch()

    files = config._find_config_files()

    assert len(files) == 3
    assert str(files[-1]).endswith("config.yaml") and "core" not in str(files[-1]) and "plugins" not in str(files[-1])


def test_deep_merge():
    """Test deep merge logic."""
    base = {
        "network": {
            "ssid": "base",
            "pass": "base",
            "ip": "1.1.1.1"
        },
        "tools": ["vim", "git"]
    }

    update = {
        "network": {
            "ssid": "update"
        },
        "tools": ["nano"]
    }

    config._deep_merge(base, update)

    assert base["network"]["ssid"] == "update"
    assert base["network"]["pass"] == "base"
    assert base["network"]["ip"] == "1.1.1.1"
    assert base["tools"] == ["nano"]


def test_config_override_hierarchy(clean_env):
    """Test full config loading hierarchy."""
    root = clean_env

    plugin_config = {
        "test_section": {
            "plugin_val": "plugin",
            "common_val": "plugin"
        }
    }
    with open(root / "plugins/myplugin/config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(plugin_config, f)

    core_config = {
        "test_section": {
            "core_val": "core",
            "common_val": "core",
            "root_val": "core_override"
        }
    }
    with open(root / "core/config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(core_config, f)

    root_config = {
        "test_section": {
            "root_val": "root",
            "common_val": "root"
        }
    }
    with open(root / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(root_config, f)

    full_config = config._load_and_merge_configs()
    section = full_config["test_section"]

    assert section["plugin_val"] == "plugin"
    assert section["core_val"] == "core"
    assert section["root_val"] == "root"
    assert section["common_val"] == "root"


def test_load_config_returns_yaml_values(monkeypatch):
    """Test that load_config returns YAML values without prompting."""

    def mock_input(_):
        raise RuntimeError("Input should not be called")

    monkeypatch.setattr('builtins.input', mock_input)

    test_config_data = {
        "op1": {
            "key1": "provided",
            "key2": "default"
        }
    }

    with patch("lib.config._load_and_merge_configs", return_value=test_config_data):
        res = config.load_config("op1")
        assert res["key1"] == "provided"
        assert res["key2"] == "default"


def test_resolve_config_values_reports_missing_required_keys():
    """Test pre-prompt resolution and missing-key detection."""
    required_configs = {
        "hostname": {"type": "str", "prompt": "Enter hostname"},
        "username": {"type": "str", "prompt": "Enter username"},
        "locale": {"type": "str", "default": "en_US.UTF-8"},
    }
    test_config_data = {
        "op_resolve": {
            "hostname": "my-host"
        }
    }

    with patch("lib.config._load_and_merge_configs", return_value=test_config_data):
        values, missing = config.resolve_config_values("op_resolve", required_configs)

    assert values["hostname"] == "my-host"
    assert values["locale"] == "en_US.UTF-8"
    assert missing == ["username"]


def test_config_null_no_prompt(monkeypatch):
    """Test that explicit null in config results in None value without prompting."""

    def mock_input(_):
        raise RuntimeError("Input should not be called")

    monkeypatch.setattr('builtins.input', mock_input)

    test_config_data = {
        "op_null": {
            "key1": None,
            "key2": "default"
        }
    }

    with patch("lib.config._load_and_merge_configs", return_value=test_config_data):
        res = config.load_config("op_null")
        assert res["key1"] is None
        assert res["key2"] == "default"
