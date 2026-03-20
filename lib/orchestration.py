"""Cross-module orchestration helpers for operation execution."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import pkgutil
from typing import Any
from typing import cast

from lib.managers import BaseManager, get_multi_selection
from lib.operations import OperationBase, OperationLogRecord, OperationRunReport, OperationAbortedError


@dataclass
class OperationSpec:
    """One operation reference resolved from orchestration config.

    Args:
        moduleName (str): Operation module name, for example 'hostname'.
        operationName (str): Operation name, for example 'username'.
    """

    moduleName: str
    operationName: str


def build_operation_registry() -> dict[str, dict[str, OperationBase]]:
    """Build available operation instances grouped by module.

    Returns:
        dict[str, dict[str, OperationBase]]: Registry by module then operation name.
    """

    _import_operation_modules('core')
    _import_operation_modules('plugins')

    operations: list[OperationBase] = []
    for operationClass in sorted(_iter_operation_subclasses(OperationBase), key=lambda cls: (cls.__module__, cls.__name__)):
        if not _is_registry_operation_class(operationClass):
            continue
        try:
            operationFactory = cast(Any, operationClass)
            operations.append(operationFactory())
        except TypeError as exc:
            raise ValueError(
                f'Operation class {operationClass.__module__}.{operationClass.__name__} must support no-arg construction.'
            ) from exc

    registry: dict[str, dict[str, OperationBase]] = {}
    for operation in operations:
        moduleRegistry = registry.setdefault(operation.moduleName, {})
        if operation.name in moduleRegistry:
            raise ValueError(f'Duplicate operation discovered: {operation.moduleName}.{operation.name}')
        moduleRegistry[operation.name] = operation
    return registry


def _is_registry_operation_class(operationClass: type[OperationBase]) -> bool:
    """Return True when an operation class belongs to a discoverable module path."""

    moduleName = operationClass.__module__
    return moduleName.startswith('core.') or moduleName.startswith('plugins.')


def _import_operation_modules(packageName: str) -> None:
    """Import all modules under a package to register operation subclasses."""

    try:
        package = importlib.import_module(packageName)
    except ModuleNotFoundError:
        return

    packagePath = getattr(package, '__path__', None)
    if packagePath is None:
        return

    for moduleInfo in pkgutil.iter_modules(packagePath, prefix=f'{packageName}.'):
        shortName = moduleInfo.name.rsplit('.', 1)[-1]
        if shortName.startswith('_'):
            continue
        importlib.import_module(moduleInfo.name)


def _iter_operation_subclasses(baseClass: type[OperationBase]) -> list[type[OperationBase]]:
    """Return all recursive subclasses for an operation base class."""

    subclasses: list[type[OperationBase]] = []
    for subClass in baseClass.__subclasses__():
        subclasses.append(subClass)
        subclasses.extend(_iter_operation_subclasses(subClass))
    return subclasses


def parse_orchestrations_from_config(mergedConfig: dict[str, Any]) -> dict[str, list[OperationSpec]]:
    """Parse orchestration definitions from merged config.

    Additional info (multi-line): supports both preferred and shorthand shapes.

    Preferred shape:
        orchestrations:
          genSetup:
            hostname: [hostname, username]
            region: [timezone]

    Shorthand shape:
        genSetup:
          - hostname:
              - hostname
              - username
          - region:
              - timezone

    Args:
        mergedConfig (dict[str, Any]): Full merged config tree.

    Returns:
        dict[str, list[OperationSpec]]: Orchestration names to operation specs.
    """

    orchestrationDefs: dict[str, Any] = {}

    orchestrationsValue = mergedConfig.get('orchestrations')
    if orchestrationsValue is None:
        pass
    elif isinstance(orchestrationsValue, dict):
        orchestrationDefs.update(orchestrationsValue)
    else:
        raise ValueError("Invalid orchestration config: 'orchestrations' must be a mapping.")

    for key, value in mergedConfig.items():
        if key == 'orchestrations':
            continue
        if not isinstance(value, list):
            continue
        parsedSpecs = _parse_orchestration_body(value, strict=False, context=f'orchestration {key}')
        if parsedSpecs:
            orchestrationDefs.setdefault(key, value)

    parsed: dict[str, list[OperationSpec]] = {}
    for orchestrationName, body in orchestrationDefs.items():
        specs = _parse_orchestration_body(body, strict=True, context=f'orchestration {orchestrationName}')
        if specs:
            parsed[orchestrationName] = specs

    return parsed


def _parse_orchestration_body(body: Any, strict: bool, context: str) -> list[OperationSpec]:
    """Parse one orchestration body into operation specs."""

    if isinstance(body, dict):
        return _parse_module_mapping(body, strict, context)

    if isinstance(body, list):
        return _parse_module_list(body, strict, context)

    if strict:
        raise ValueError(f'Invalid {context}: expected mapping or list, got {type(body).__name__}.')

    return []


def _parse_module_mapping(mappingBody: dict[str, Any], strict: bool, context: str) -> list[OperationSpec]:
    """Parse mapping body format into operation specs."""

    specs: list[OperationSpec] = []
    for moduleName, operationsValue in mappingBody.items():
        moduleNameStr = str(moduleName)
        opNames = _coerce_operation_names(operationsValue)
        if strict and not opNames:
            raise ValueError(
                f'Invalid {context}: module {moduleNameStr} must map to a non-empty string, list of strings, '
                'or mapping with ops/operations.'
            )
        for operationName in opNames:
            specs.append(OperationSpec(moduleNameStr, operationName))
    return specs


def _parse_module_list(listBody: list[Any], strict: bool, context: str) -> list[OperationSpec]:
    """Parse list body format into operation specs."""

    specs: list[OperationSpec] = []
    for idx, item in enumerate(listBody):
        if not isinstance(item, dict):
            if strict:
                raise ValueError(f'Invalid {context}: list item at index {idx} must be a mapping.')
            continue
        specs.extend(_parse_module_mapping(item, strict, context))

    if strict and not specs:
        raise ValueError(f'Invalid {context}: no valid operations were provided.')

    return specs


def _coerce_operation_names(value: Any) -> list[str]:
    """Convert operation values to normalized operation name list."""

    if isinstance(value, dict):
        nestedOps = value.get('operations')
        if nestedOps is None:
            nestedOps = value.get('ops')
        if nestedOps is None:
            return []
        return _coerce_operation_names(nestedOps)

    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []

    if isinstance(value, list):
        opNames: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                opNames.append(item.strip())
        return opNames

    return []


def resolve_operations(
    specs: list[OperationSpec],
    registry: dict[str, dict[str, OperationBase]],
) -> list[OperationBase]:
    """Resolve operation specs into concrete operation instances.

    Args:
        specs (list[OperationSpec]): Parsed operation specs.
        registry (dict[str, dict[str, OperationBase]]): Available operation registry.

    Returns:
        list[OperationBase]: Ordered unique operation instances.

    Raises:
        ValueError: Unknown module or operation in specs.
    """

    resolved: list[OperationBase] = []
    seenKeys: set[tuple[str, str]] = set()

    for spec in specs:
        moduleOps = registry.get(spec.moduleName)
        if moduleOps is None:
            raise ValueError(f'Unknown orchestration module: {spec.moduleName}')

        operation = moduleOps.get(spec.operationName)
        if operation is None:
            raise ValueError(f'Unknown operation for module {spec.moduleName}: {spec.operationName}')

        opKey = (spec.moduleName, spec.operationName)
        if opKey in seenKeys:
            continue

        seenKeys.add(opKey)
        resolved.append(operation)

    return resolved


def choose_custom_operations(registry: dict[str, dict[str, OperationBase]]) -> list[OperationBase]:
    """Interactively select multiple operations across modules.

    Args:
        registry (dict[str, dict[str, OperationBase]]): Operation registry.

    Returns:
        list[OperationBase]: User-selected operations in selection order.
    """

    operationChoices: list[tuple[str, str, OperationBase]] = []
    for moduleName in sorted(registry):
        for operationName in sorted(registry[moduleName]):
            operationChoices.append((moduleName, operationName, registry[moduleName][operationName]))

    labels = [f'{moduleName}.{operationName}' for moduleName, operationName, _ in operationChoices]
    selectedIndices = get_multi_selection(
        labels,
        'Select operations (Space toggles, Enter confirms; no selections returns to menu):',
    )
    if not selectedIndices:
        return []

    selected: list[OperationBase] = []
    for idx in selectedIndices:
        if idx < 0 or idx >= len(operationChoices):
            continue
        _, _, operation = operationChoices[idx]
        selected.append(operation)

    return selected


def run_operations_with_manager(mgr: BaseManager, operations: list[OperationBase], selectedName: str) -> OperationRunReport:
    """Run operations with preflight config gather and aggregated reporting.

    Args:
        mgr (BaseManager): Active manager context.
        operations (list[OperationBase]): Operations to execute in order.
        selectedName (str): Selected orchestration label for reporting.

    Returns:
        OperationRunReport: Aggregate operation report.

    Raises:
        Exception: Re-raises uncaught operation exceptions after fatal log.
    """

    mgr.clear_operation_logs()
    currentOperationName = selectedName

    try:
        preparedOperations: list[tuple[OperationBase, dict[str, Any]]] = []
        for operation in operations:
            currentOperationName = operation.name
            try:
                preparedConfigs = operation.gather_config(mgr)
                preparedOperations.append((operation, preparedConfigs))
            except OperationAbortedError as abortEx:
                mgr.log_operation(OperationLogRecord(currentOperationName, False, None, f"Skipped: {abortEx}", [], False))
                continue

        for operation, preparedConfigs in preparedOperations:
            currentOperationName = operation.name
            operation.execute_with_config(mgr, preparedConfigs)
    except (Exception, KeyboardInterrupt) as exc:
        fatalRecord = OperationLogRecord(currentOperationName, False, None, None, [str(exc)], True)
        mgr.log_operation(fatalRecord)
        report = OperationRunReport(records=_collect_log_records(mgr.get_operation_logs()), selectedOperation=selectedName)
        _print_report(report)
        raise

    report = OperationRunReport(records=_collect_log_records(mgr.get_operation_logs()), selectedOperation=selectedName)
    _print_report(report)
    return report


def _collect_log_records(rawLogs: list[Any]) -> list[OperationLogRecord]:
    """Filter manager logs to operation log records."""

    return [entry for entry in rawLogs if isinstance(entry, OperationLogRecord)]


def _print_report(report: OperationRunReport) -> None:
    """Print concise report for orchestration execution."""

    if not report.records:
        print('No operations executed.')
        return

    records = report.records
    changed = sum(1 for record in records if record.changed)
    errors = [err for record in records for err in record.errors]

    print('\nOperation summary:')
    print(f'{changed} changes of {len(report.records)} operations.')
    if changed:
        print("The following changes were made:")
        for record in records:
            if record.changed:
                print(f"- {record.operationName}: {record.summary()}")
        print("These operations did not result in any changes:")
        for record in records:
            if not record.changed:
                print(f"- {record.operationName}: {record.summary()}")
    if errors:
        print('Encountered errors during hostname setup:')
        for record in records:
            if record.errors:
                for error in record.errors:
                    print(f'- {record.operationName}: {error}')

__all__ = [
    'OperationSpec',
    'build_operation_registry',
    'parse_orchestrations_from_config',
    'resolve_operations',
    'choose_custom_operations',
    'run_operations_with_manager',
]
