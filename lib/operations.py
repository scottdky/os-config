from __future__ import annotations

import sys
import argparse
import getpass
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.config import resolve_config_values
from lib.managers import BaseManager, get_user_selection, interactive_create_manager

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

    def execute(self, mgr: BaseManager) -> bool:
        """Resolve config then apply this operation.

        Args:
            mgr (BaseManager): Active manager instance.

        Returns:
            bool: True if this operation made a change.
        """
        allConfigs = self.gather_config(mgr)
        return self.apply(mgr, allConfigs)

    @abstractmethod
    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> bool:
        """Apply this operation using resolved config.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Final resolved config values.

        Returns:
            bool: True if any change was made.
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
        sel = get_user_selection(choices, prompt, False)
        return sel if sel is not None else -1


class OperationPipeline:
    """Compose one or more operations behind a shared CLI entrypoint."""

    def __init__(self, operations: list[OperationBase], managerFactory: Callable[[], BaseManager | None] = interactive_create_manager) -> None:
        if not operations:
            raise ValueError('OperationPipeline requires at least one operation')
        self.operations = operations
        self.managerFactory = managerFactory

    def run_cli(self, parserDescription: str) -> int:
        """Run operation selection and execute one or all operations.

        Args:
            parserDescription (str): Description shown by argparse help.

        Returns:
            int: Process-style exit code (0 success/no-op, 1 changed).
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
            selectedIdx = get_user_selection(choices, 'Select operation to perform:')
            if selectedIdx is None:
                print('No operation selected. Exiting.')
                return 0
            selectedOperation = choices[selectedIdx]

        manager = self.managerFactory()
        if manager is None:
            print('No manager selected. Exiting.')
            return 0

        with manager as mgr:
            changed = False
            if selectedOperation == 'all':
                for operation in self.operations:
                    changed |= operation.execute(mgr)
            else:
                matchingOperation = next((op for op in self.operations if op.name == selectedOperation), None)
                if matchingOperation is None:
                    print(f'Unknown operation: {selectedOperation}')
                    return 0
                changed = matchingOperation.execute(mgr)

            return 1 if changed else 0


__all__ = ['OperationBase', 'OperationPipeline', 'get_user_selection']
