"""Unit tests for orchestration parsing and operation resolution."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.orchestration import (
    OperationSpec,
    build_operation_registry,
    choose_custom_operations,
    parse_orchestrations_from_config,
    resolve_operations,
)


@pytest.mark.unit
def test_build_operation_registry_discovers_core_operations():
    """Dynamic discovery should include known core operations."""

    registry = build_operation_registry()

    assert 'hostname' in registry
    assert 'region' in registry
    assert {'hostname', 'username', 'password'}.issubset(set(registry['hostname'].keys()))
    assert {'timezone', 'locale'}.issubset(set(registry['region'].keys()))


@pytest.mark.unit
def test_parse_orchestrations_from_preferred_shape():
    """Parses preferred orchestrations mapping shape."""

    mergedConfig = {
        'orchestrations': {
            'genSetup': {
                'hostname': ['hostname', 'username'],
                'region': ['timezone'],
            }
        }
    }

    parsed = parse_orchestrations_from_config(mergedConfig)

    assert 'genSetup' in parsed
    assert parsed['genSetup'] == [
        OperationSpec('hostname', 'hostname'),
        OperationSpec('hostname', 'username'),
        OperationSpec('region', 'timezone'),
    ]


@pytest.mark.unit
def test_parse_orchestrations_from_list_shape():
    """Parses shorthand list-of-module-mappings shape."""

    mergedConfig = {
        'genSetup': [
            {'hostname': ['hostname', 'username']},
            {'region': ['timezone']},
        ]
    }

    parsed = parse_orchestrations_from_config(mergedConfig)

    assert 'genSetup' in parsed
    assert parsed['genSetup'] == [
        OperationSpec('hostname', 'hostname'),
        OperationSpec('hostname', 'username'),
        OperationSpec('region', 'timezone'),
    ]


@pytest.mark.unit
def test_parse_orchestrations_supports_module_metadata_shape():
    """Parses module mappings that carry operations under operations/ops keys."""

    mergedConfig = {
        'orchestrations': {
            'genSetup': {
                'hostname': {
                    'operations': ['hostname', 'username'],
                    'description': 'host setup',
                },
                'region': {
                    'ops': ['timezone'],
                },
            }
        }
    }

    parsed = parse_orchestrations_from_config(mergedConfig)

    assert 'genSetup' in parsed
    assert parsed['genSetup'] == [
        OperationSpec('hostname', 'hostname'),
        OperationSpec('hostname', 'username'),
        OperationSpec('region', 'timezone'),
    ]


@pytest.mark.unit
def test_parse_orchestrations_ignores_non_orchestration_top_level_mappings():
    """Regular operation config sections should not be auto-detected as orchestrations."""

    mergedConfig = {
        'region': {
            'locale': 'en_US.UTF-8',
        },
        'rtc': {
            'device': 'mcp7941x',
            'addr': None,
            'sdapin': 22,
        },
    }

    parsed = parse_orchestrations_from_config(mergedConfig)

    assert parsed == {}


@pytest.mark.unit
def test_resolve_operations_deduplicates_preserves_order():
    """Resolve keeps first-seen order and de-duplicates identical specs."""

    registry = build_operation_registry()
    specs = [
        OperationSpec('hostname', 'hostname'),
        OperationSpec('hostname', 'hostname'),
        OperationSpec('region', 'locale'),
        OperationSpec('hostname', 'username'),
    ]

    resolved = resolve_operations(specs, registry)

    assert [op.name for op in resolved] == ['hostname', 'locale', 'username']


@pytest.mark.unit
def test_resolve_operations_unknown_module_raises():
    """Unknown module should raise clear ValueError."""

    registry = build_operation_registry()

    with pytest.raises(ValueError, match='Unknown orchestration module'):
        resolve_operations([OperationSpec('unknown', 'hostname')], registry)


@pytest.mark.unit
def test_resolve_operations_unknown_operation_raises():
    """Unknown operation should raise clear ValueError."""

    registry = build_operation_registry()

    with pytest.raises(ValueError, match='Unknown operation for module hostname'):
        resolve_operations([OperationSpec('hostname', 'nope')], registry)


@pytest.mark.unit
def test_choose_custom_operations_supports_multi_select(monkeypatch):
    """Custom chooser should return all selected operations from one multi-select prompt."""

    registry = build_operation_registry()
    monkeypatch.setattr('lib.orchestration.get_multi_selection', lambda *args, **kwargs: [0, 2])

    selected = choose_custom_operations(registry)

    assert [op.name for op in selected] == ['hostname', 'username']
