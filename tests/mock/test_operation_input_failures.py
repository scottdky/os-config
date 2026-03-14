"""Mock tests for interactive input failure and cancellation paths."""

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import lib.operations as operationsModule
from lib.managers import BaseManager, CommandResult
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class _DummyManager(BaseManager):
    """Minimal concrete manager for pipeline/input mock tests."""

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


class _PromptInputOperation(OperationBase):
    """Operation that prompts for required value to simulate input failures."""

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, object]] = {
            'value': {
                'type': 'str',
                'prompt': 'Enter value',
            }
        }
        super().__init__(moduleName='test', name='prompt-op', requiredConfigs=requiredConfigs)
        self.applyCalls = 0

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, object]) -> dict[str, object]:
        _ = mgr, configsToPrompt
        value = self._prompt_text_value('Enter value')
        return {'value': value}

    def apply(self, mgr: BaseManager, configs: dict[str, object]) -> OperationLogRecord:
        _ = mgr, configs
        self.applyCalls += 1
        return OperationLogRecord(operationName=self.name, changed=True)


@pytest.mark.mock
def test_run_cli_exits_when_operation_menu_cancelled(monkeypatch):
    """Pipeline should exit cleanly when operation selection is canceled."""
    pipeline = OperationPipeline(operations=[_PromptInputOperation()], managerFactory=_DummyManager)

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation=None))
    monkeypatch.setattr(operationsModule, 'get_single_selection', lambda choices, prompt, addExit='Exit': None)

    report = pipeline.run_cli('prompt failure test')

    assert report.records == []
    assert report.selectedOperation == ''


@pytest.mark.mock
def test_run_cli_exits_when_manager_selection_cancelled(monkeypatch):
    """Pipeline should exit cleanly when manager selection is canceled."""
    pipeline = OperationPipeline(operations=[_PromptInputOperation()], managerFactory=lambda: None)

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='prompt-op'))

    report = pipeline.run_cli('manager cancel test')

    assert report.records == []
    assert report.selectedOperation == 'prompt-op'


@pytest.mark.mock
def test_pipeline_aborts_on_keyboard_interrupt_during_prompt(monkeypatch):
    """Prompt interruption should abort run and prevent apply execution."""
    manager = _DummyManager()
    operation = _PromptInputOperation()
    pipeline = OperationPipeline(operations=[operation], managerFactory=lambda: manager)

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='prompt-op'))
    monkeypatch.setattr(operationsModule, 'resolve_config_values', lambda moduleName, requiredConfigs: ({}, ['value']))
    monkeypatch.setattr('builtins.input', lambda prompt='': (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        pipeline.run_cli('keyboard interrupt test')

    assert operation.applyCalls == 0
    logs = manager.get_operation_logs()
    assert len(logs) == 1
    assert logs[0].fatal is True
    assert logs[0].operationName == 'prompt-op'


@pytest.mark.mock
def test_pipeline_aborts_on_eoferror_during_prompt(monkeypatch):
    """EOF during prompt should abort run and prevent apply execution."""
    manager = _DummyManager()
    operation = _PromptInputOperation()
    pipeline = OperationPipeline(operations=[operation], managerFactory=lambda: manager)

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', lambda self: argparse.Namespace(operation='prompt-op'))
    monkeypatch.setattr(operationsModule, 'resolve_config_values', lambda moduleName, requiredConfigs: ({}, ['value']))
    monkeypatch.setattr('builtins.input', lambda prompt='': (_ for _ in ()).throw(EOFError('input stream closed')))

    with pytest.raises(EOFError, match='input stream closed'):
        pipeline.run_cli('eof prompt test')

    assert operation.applyCalls == 0
    logs = manager.get_operation_logs()
    assert len(logs) == 1
    assert logs[0].fatal is True
    assert logs[0].operationName == 'prompt-op'
