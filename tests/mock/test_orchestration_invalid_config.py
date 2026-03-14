"""Mock tests for orchestration config validation failures."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import install
from lib.orchestration import parse_orchestrations_from_config


@pytest.mark.mock
def test_parse_raises_when_orchestrations_is_not_mapping():
    """Explicit orchestrations value must be a mapping."""

    with pytest.raises(ValueError, match="'orchestrations' must be a mapping"):
        parse_orchestrations_from_config({'orchestrations': ['hostname']})


@pytest.mark.mock
def test_parse_raises_on_invalid_module_operations_shape():
    """Module operations must be non-empty string or string list."""

    mergedConfig = {
        'orchestrations': {
            'genSetup': {
                'hostname': {'invalid': 'shape'},
            }
        }
    }

    with pytest.raises(ValueError, match='hostname must map to a non-empty string, list of strings, or mapping with ops/operations'):
        parse_orchestrations_from_config(mergedConfig)


@pytest.mark.mock
def test_run_install_cli_surfaces_invalid_config_error(monkeypatch):
    """CLI should surface orchestration config validation errors."""

    monkeypatch.setattr(install, 'load_merged_config', lambda: {'orchestrations': 'invalid'})

    with pytest.raises(ValueError, match="'orchestrations' must be a mapping"):
        install.run_install_cli()
