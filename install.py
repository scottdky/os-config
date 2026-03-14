#!/usr/bin/env python3
"""Project-level orchestration CLI across operation modules."""

from __future__ import annotations

from lib.config import load_merged_config
from lib.managers import interactive_create_manager, get_single_selection
from lib.orchestration import (
    build_operation_registry,
    choose_custom_operations,
    parse_orchestrations_from_config,
    resolve_operations,
    run_operations_with_manager,
)


def run_install_cli() -> None:
    """Run interactive install orchestration selection and execution flow."""

    mergedConfig = load_merged_config()
    registry = build_operation_registry()
    definedOrchestrations = parse_orchestrations_from_config(mergedConfig)

    choices = list(sorted(definedOrchestrations.keys()))
    customLabel = 'custom (manual operation selection)'
    choices.append(customLabel)

    while True:
        selectedIdx = get_single_selection(choices, 'Select orchestration to run:', addExit='Exit')
        if selectedIdx is None:
            print('No orchestration selected. Exiting.')
            return

        selectedChoice = choices[selectedIdx]

        if selectedChoice == customLabel:
            operations = choose_custom_operations(registry)
            if not operations:
                print('No operations selected. Returning to main menu.')
                continue
            selectedName = 'custom'
        else:
            specs = definedOrchestrations.get(selectedChoice, [])
            operations = resolve_operations(specs, registry)
            if not operations:
                print(f'Orchestration {selectedChoice} has no valid operations. Exiting.')
                return
            selectedName = selectedChoice

        manager = interactive_create_manager()
        if manager is None:
            print('No manager selected. Exiting.')
            return

        with manager as mgr:
            run_operations_with_manager(mgr, operations, selectedName)
        return


if __name__ == '__main__':
    run_install_cli()
