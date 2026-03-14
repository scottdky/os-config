from __future__ import annotations

import sys
import argparse
import getpass
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.config import resolve_config_values
from lib.managers import BaseManager, get_single_selection, interactive_create_manager


@dataclass
class OperationLogRecord:
    """Structured result for one operation execution.

    Additional info (multi-line): this is the operation-level payload used by
    the current pipeline and future orchestration/reporting layers.

    Args:
        operationName (str): Name of the operation that produced this record.
        changed (bool): Whether the operation changed target state.
        previousState (Any | None): Value/state before the operation.
        currentState (Any | None): Value/state after the operation.
        errors (list[str]): Non-fatal errors captured by the operation.
        fatal (bool): Whether this record reflects a fatal uncaught exception.
    """
    operationName: str
    changed: bool
    previousState: Any | None = None
    currentState: Any | None = None
    errors: list[str] = field(default_factory=list)
    fatal: bool = False

    def summary(self) -> str:
        """Generate a concise summary of this operation record."""
        if self.fatal:
            return f"Failed with error: {self.errors[0] if self.errors else 'Unknown error'}"
        if self.changed:
            return f"Changed from '{self.previousState}' to '{self.currentState}'"
        return "No change"


@dataclass
class OperationRunReport:
    """Aggregate report for one pipeline run.

    Args:
        records (list[OperationLogRecord]): Operation records in execution order.
        selectedOperation (str): Operation selected by user or 'all'.
    """
    records: list[OperationLogRecord] = field(default_factory=list)
    selectedOperation: str = ''

    @property
    def changed(self) -> bool:
        """Return True when any operation changed target state."""
        return any(record.changed for record in self.records)

    @property
    def hasErrors(self) -> bool:
        """Return True when any operation recorded one or more errors."""
        return any(record.errors for record in self.records)

    @property
    def hasFatal(self) -> bool:
        """Return True when any operation record is marked fatal."""
        return any(record.fatal for record in self.records)

class OperationBase(ABC):
    """Base class for one concrete operation.

    Additional info (multi-line): each operation owns one config schema (in the
    same dict shape expected by `lib.config`) and one execution path. Use
    `OperationPipeline` to compose multiple operations.

    Args:
        moduleName (str): Top-level config section to read.
        name (str): Operation name used in CLI selection.
        requiredConfigs (dict[str, dict[str, object]]): Config schema used by
            `resolve_config_values` and operation-level prompting.
    """

    def __init__(self, moduleName: str, name: str, requiredConfigs: dict[str, dict[str, object]]) -> None:
        self.moduleName = moduleName
        self.name = name
        self.requiredConfigs = requiredConfigs

    def gather_config(self, mgr: BaseManager) -> dict[str, Any]:
        """Resolve and prompt config for this operation.

        Args:
            mgr (BaseManager): Active manager instance.

        Returns:
            dict[str, Any]: Resolved config values for this operation.
        """
        allConfigsRaw, missingKeysRaw = resolve_config_values(self.moduleName, self.requiredConfigs)
        allConfigs: dict[str, Any] = dict(allConfigsRaw)
        missingKeys = list(missingKeysRaw)

        if missingKeys:
            configsToPrompt = {key: allConfigs.get(key) for key in missingKeys}
            promptedValues = self.prompt_missing_values(mgr, configsToPrompt)
            if not isinstance(promptedValues, dict):
                raise ValueError('prompt_missing_values must return a dict[str, Any] of prompted values')
            allConfigs.update(promptedValues)

        self.validate_config_values(allConfigs)
        return allConfigs

    @abstractmethod
    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any]) -> dict[str, Any]:
        """Prompt and collect missing values.

        Additional info (multi-line): subclasses own prompting behavior
        (text/menu/secure) for unresolved keys and must return key-value pairs
        to merge into resolved config.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys that need prompts.

        Returns:
            dict[str, Any]: Prompted key-value pairs.
        """
        raise NotImplementedError

    def validate_config_values(self, allConfigs: dict[str, Any]) -> None:
        """Validate final prompted values.

        Args:
            allConfigs (dict[str, Any]): Config values to validate.

        Raises:
            ValueError: If required values remain unresolved.
        """
        missingRequired = []
        for key in self.requiredConfigs:
            if key not in allConfigs:
                missingRequired.append(key)
                continue
            value = allConfigs.get(key)
            if value is None:
                missingRequired.append(key)
            elif isinstance(value, str) and value == '':
                missingRequired.append(key)

        if missingRequired:
            joined = ', '.join(missingRequired)
            raise ValueError(f'Missing required config values: {joined}')

    def execute(self, mgr: BaseManager) -> OperationLogRecord:
        """Resolve config then apply this operation.

        Args:
            mgr (BaseManager): Active manager instance.

        Returns:
            OperationLogRecord: Structured operation execution record.
        """
        allConfigs = self.gather_config(mgr)
        return self.execute_with_config(mgr, allConfigs)

    def execute_with_config(self, mgr: BaseManager, allConfigs: dict[str, Any]) -> OperationLogRecord:
        """Apply this operation using pre-resolved config.

        Args:
            mgr (BaseManager): Active manager instance.
            allConfigs (dict[str, Any]): Pre-resolved config values.

        Returns:
            OperationLogRecord: Structured operation execution record.
        """
        rawResult = self.apply(mgr, allConfigs)
        if isinstance(rawResult, OperationLogRecord):
            result = rawResult
            if result.operationName == '':
                result.operationName = self.name
        else:
            result = OperationLogRecord(operationName=self.name, changed=bool(rawResult))

        mgr.log_operation(result)
        return result

    @abstractmethod
    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord | bool:
        """Apply this operation using resolved config.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Final resolved config values.

        Returns:
            OperationLogRecord | bool: Structured execution record.

            Additional info (multi-line): bool is temporarily allowed for
            backward compatibility with operations not yet migrated to
            `OperationLogRecord`.
        """
        raise NotImplementedError

    @staticmethod
    def _get_prompt_text(prompt: str, defaultValue: str = '') -> str:
        """Construct prompt text where a default value is specified."""
        if '{default}' in prompt:
            prompt = prompt.format(default=defaultValue)
        if not prompt.endswith(': '):
            prompt += ': '
        return prompt

    @staticmethod
    def _prompt_text_value(prompt: str, defaultValue: str = '') -> str:
        """Prompt for a non-secure value and cast to schema type."""
        return input(OperationBase._get_prompt_text(prompt, defaultValue))

    @staticmethod
    def _prompt_secure_value(prompt: str) -> str:
        """Prompt for secure value with confirmation."""
        prompt = OperationBase._get_prompt_text(prompt, '')

        while True:
            value = getpass.getpass(prompt)
            if value == '':
                print('Error: a string value is required.')
                continue
            if value == getpass.getpass('Confirm value: '):
                return value
            print('Error: Values do not match. Please try again.')

    @staticmethod
    def prompt_menu_value(prompt: str, choices: list[str], defaultValue: str = '') -> int:
        """Prompt for a value using menu selection."""
        prompt = OperationBase._get_prompt_text(prompt, defaultValue)
        sel = get_single_selection(choices, prompt, False)
        return sel if sel is not None else -1


class OperationPipeline:
    """Compose one or more operations behind a shared CLI entrypoint."""

    def __init__(self, operations: list[OperationBase], managerFactory: Callable[[], BaseManager | None] = interactive_create_manager) -> None:
        if not operations:
            raise ValueError('OperationPipeline requires at least one operation')
        self.operations = operations
        self.managerFactory = managerFactory

    def run_cli(self, parserDescription: str) -> OperationRunReport:
        """Run operation selection and execute one or all operations.

        Args:
            parserDescription (str): Description shown by argparse help.

        Returns:
            OperationRunReport: Aggregate report for selected operation(s).
        """
        operationNames = [operation.name for operation in self.operations]
        choices = operationNames if len(operationNames) == 1 else [*operationNames, 'all']

        parser = argparse.ArgumentParser(description=parserDescription)
        parser.add_argument(
            'operation',
            nargs='?',
            choices=choices,
            help='Operation to perform (if omitted, interactive menu is shown)',
        )
        args = parser.parse_args()

        selectedOperation = args.operation
        if selectedOperation is None:
            selectedIdx = get_single_selection(choices, 'Select operation to perform:')
            if selectedIdx is None:
                print('No operation selected. Exiting.')
                return OperationRunReport(records=[], selectedOperation='')
            selectedOperation = choices[selectedIdx]

        manager = self.managerFactory()
        if manager is None:
            print('No manager selected. Exiting.')
            return OperationRunReport(records=[], selectedOperation=selectedOperation)

        with manager as mgr:
            mgr.clear_operation_logs()
            currentOperationName = selectedOperation
            try:
                selectedOperations: list[OperationBase] = []
                if selectedOperation == 'all':
                    selectedOperations = list(self.operations)
                else:
                    matchingOperation = next((op for op in self.operations if op.name == selectedOperation), None)
                    if matchingOperation is None:
                        print(f'Unknown operation: {selectedOperation}')
                        return OperationRunReport(records=[], selectedOperation=selectedOperation)
                    selectedOperations = [matchingOperation]

                preparedOperations: list[tuple[OperationBase, dict[str, Any]]] = []
                for operation in selectedOperations:
                    currentOperationName = operation.name
                    preparedConfigs = operation.gather_config(mgr)
                    preparedOperations.append((operation, preparedConfigs))

                for operation, preparedConfigs in preparedOperations:
                    currentOperationName = operation.name
                    operation.execute_with_config(mgr, preparedConfigs)
            except (Exception, KeyboardInterrupt) as exc:
                fatalRecord = OperationLogRecord(
                    operationName=currentOperationName,
                    changed=False,
                    previousState=None,
                    currentState=None,
                    errors=[str(exc)],
                    fatal=True,
                )
                mgr.log_operation(fatalRecord)
                report = OperationRunReport(
                    records=self._collect_log_records(mgr.get_operation_logs()),
                    selectedOperation=selectedOperation,
                )
                self._print_report(report)
                raise

            report = OperationRunReport(
                records=self._collect_log_records(mgr.get_operation_logs()),
                selectedOperation=selectedOperation,
            )
            self._print_report(report)
            return report

    @staticmethod
    def _collect_log_records(rawLogs: list[Any]) -> list[OperationLogRecord]:
        """Filter manager logs to OperationLogRecord entries.

        Args:
            rawLogs (list[Any]): Raw manager operation log entries.

        Returns:
            list[OperationLogRecord]: Typed operation log records.
        """
        return [entry for entry in rawLogs if isinstance(entry, OperationLogRecord)]

    @staticmethod
    def _print_report(report: OperationRunReport) -> None:
        """Print a concise summary for operation pipeline execution.

        Args:
            report (OperationRunReport): Aggregate report to display.
        """
        if not report.records:
            print('No operations executed.')
            return

        print('\nOperation summary:')
        for record in report.records:
            status = 'changed' if record.changed else 'no change'
            if record.errors:
                status = f'{status}, errors={len(record.errors)}'
            if record.fatal:
                status = f'{status}, fatal'
            print(f'- {record.operationName}: {status}')
            if record.previousState is not None or record.currentState is not None:
                print(f'  previous: {record.previousState}')
                print(f'  current:  {record.currentState}')
            for err in record.errors:
                print(f'  error:    {err}')


__all__ = ['OperationLogRecord', 'OperationRunReport', 'OperationBase', 'OperationPipeline']
