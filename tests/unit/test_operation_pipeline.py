"""Unit tests for structured operation pipeline reporting."""

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.managers import BaseManager, CommandResult
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class _DummyManager(BaseManager):
    """Minimal concrete manager for operation pipeline unit tests."""

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        _ = command, sudo
        return CommandResult('', '', 0)

    def exists(self, remotePath: str) -> bool:
        _ = remotePath
        return False

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        _ = localPath, remotePath, sudo
        return

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        _ = remotePath, localPath, sudo
        return


class _BoolOperation(OperationBase):
    """Operation that returns bool for backward-compatibility path."""

    def __init__(self) -> None:
        super().__init__(moduleName='test', name='bool-op', requiredConfigs={})

    def gather_config(self, mgr: BaseManager) -> dict[str, object]:
        _ = mgr
        return {}

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, object], allConfigs: dict[str, object]) -> dict[str, object]:
        _ = mgr, configsToPrompt
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, object]) -> bool:
        _ = mgr, configs
        return True


class _RecordOperation(OperationBase):
    """Operation that returns structured operation log record."""

    def __init__(self) -> None:
        super().__init__(moduleName='test', name='record-op', requiredConfigs={})

    def gather_config(self, mgr: BaseManager) -> dict[str, object]:
        _ = mgr
        return {}

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, object], allConfigs: dict[str, object]) -> dict[str, object]:
        _ = mgr, configsToPrompt
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, object]) -> OperationLogRecord:
        _ = mgr, configs
        return OperationLogRecord(
            operationName=self.name,
            changed=False,
            previousState='old',
            currentState='new',
            errors=['simulated warning'],
        )


class _FailingOperation(OperationBase):
    """Operation that raises uncaught exception to validate fatal flow."""

    def __init__(self) -> None:
        super().__init__(moduleName='test', name='failing-op', requiredConfigs={})

    def gather_config(self, mgr: BaseManager) -> dict[str, object]:
        _ = mgr
        return {}

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, object], allConfigs: dict[str, object]) -> dict[str, object]:
        _ = mgr, configsToPrompt
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, object]) -> OperationLogRecord:
        _ = mgr, configs
        raise RuntimeError('boom')


class _TrackingOperation(OperationBase):
    """Operation that tracks gather/apply calls for flow assertions."""

    def __init__(self, name: str, gatherException: Exception | None = None) -> None:
        super().__init__(moduleName='test', name=name, requiredConfigs={})
        self.gatherCalls = 0
        self.applyCalls = 0
        self.gatherException = gatherException

    def gather_config(self, mgr: BaseManager) -> dict[str, object]:
        _ = mgr
        self.gatherCalls += 1
        if self.gatherException is not None:
            raise self.gatherException
        return {'ok': True}

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, object], allConfigs: dict[str, object]) -> dict[str, object]:
        _ = mgr, configsToPrompt
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, object]) -> OperationLogRecord:
        _ = mgr, configs
        self.applyCalls += 1
        return OperationLogRecord(operationName=self.name, changed=True)


@pytest.mark.unit
def test_execute_coerces_bool_to_record_and_logs():
    """Bool apply result should be wrapped in OperationLogRecord and stored."""
    manager = _DummyManager()
    operation = _BoolOperation()

    record = operation.execute(manager)

    assert record.operationName == 'bool-op'
    assert record.changed is True
    assert record.errors == []
    assert len(manager.get_operation_logs()) == 1


@pytest.mark.unit
def test_pipeline_returns_aggregate_report(monkeypatch):
    """Pipeline should aggregate records and report changed/error state."""
    pipeline = OperationPipeline(
        operations=[_BoolOperation(), _RecordOperation()],
        managerFactory=_DummyManager,
    )

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='all'))

    report = pipeline.run_cli('test pipeline')

    assert report.selectedOperation == 'all'
    assert len(report.records) == 2
    assert report.changed is True
    assert report.hasErrors is True
    assert report.hasFatal is False


@pytest.mark.unit
def test_pipeline_adds_fatal_record_on_uncaught_exception(monkeypatch):
    """Pipeline should log fatal record and re-raise uncaught exceptions."""
    pipeline = OperationPipeline(
        operations=[_BoolOperation(), _FailingOperation()],
        managerFactory=_DummyManager,
    )

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='all'))

    with pytest.raises(RuntimeError, match='boom'):
        pipeline.run_cli('test pipeline fatal')


@pytest.mark.unit
def test_execute_does_not_call_apply_when_gather_config_fails():
    """Operation execute should abort before apply when config gather fails."""
    manager = _DummyManager()
    operation = _TrackingOperation(name='needs-config', gatherException=ValueError('missing config'))

    with pytest.raises(ValueError, match='missing config'):
        operation.execute(manager)

    assert operation.gatherCalls == 1
    assert operation.applyCalls == 0
    assert manager.get_operation_logs() == []


@pytest.mark.unit
def test_pipeline_all_preflight_aborts_before_any_apply(monkeypatch):
    """All-mode should gather configs for all operations before any apply runs."""
    manager = _DummyManager()
    first = _TrackingOperation(name='first-op')
    second = _TrackingOperation(name='second-op', gatherException=ValueError('config missing for second-op'))
    pipeline = OperationPipeline(
        operations=[first, second],
        managerFactory=lambda: manager,
    )

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='all'))

    with pytest.raises(SystemExit):
        pipeline.run_cli('test preflight abort')

    assert first.gatherCalls == 1
    assert second.gatherCalls == 1
    assert first.applyCalls == 0
    assert second.applyCalls == 0
    logs = manager.get_operation_logs()
    assert len(logs) == 1
    assert logs[0].fatal is True
    assert logs[0].operationName == 'second-op'
