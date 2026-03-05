#!/usr/bin/env python3

"""Utilities for operation configuration loading and prompting.

Additional info (multi-line): this module defines the contract between
operation schemas (``REQUIRED_CONFIGS`` in Python modules) and YAML values
(``config.yaml`` hierarchy).

REQUIRED_CONFIGS field schema (per key):
        - ``type`` (str, optional): cast hint for prompted input. Supported aliases:
            bool/int/float/str.
        - ``prompt`` (str, optional): prompt text. May include ``{default}``.
        - ``default`` (Any, optional): static fallback used when YAML key is missing.
        - ``secure`` (bool, optional): if true, prompt using hidden input with
            confirmation (for secrets like passwords).

YAML value rules (per operation section):
        - Key present with value -> use that value.
        - Key present with ``null`` -> explicit None value.
        - Key missing -> unresolved; if key exists in REQUIRED_CONFIGS and no static
            default applies, it is reported as missing and prompted later.

Resolution flow:
        1) ``resolve_config_values``: load YAML + apply static defaults + report
             missing keys (no prompting).
        2) ``validate_and_prompt``: prompt unresolved keys, optionally with runtime
             ``defaultOverrides`` (for example current target OS hostname).
"""

from typing import Any, Dict, Optional
import yaml
import os
import glob

CONFIG_FILE = 'config.yaml'

BOOL_TRUE = {"true", "yes", "on", "1"}
BOOL_FALSE = {"false", "no", "off", "0"}

TYPE_ALIASES = {
    "bool": "bool", "boolean": "bool",
    "int": "int", "integer": "int",
    "float": "float", "number": "float",
    "str": "str", "string": "str",
    # "list": "list", "seq": "list", "sequence": "list",
    # "dict": "dict", "map": "dict",
}

def _norm(s: str) -> str:
    return str(s).strip().lower()

def _parse_bool(s: str) -> bool:
    n = _norm(s)
    if n in BOOL_TRUE: return True
    if n in BOOL_FALSE: return False
    raise ValueError(f"expected boolean (true/yes/on/1 or false/no/off/0), got '{s}'")

CASTERS = {
    "bool": _parse_bool,
    "int": lambda s: int(str(s).strip()),
    "float": lambda s: float(str(s).strip()),
    "str": lambda s: str(s),
}

def _cast_value(value: str, typeName: Optional[str]) -> Any:
    """Convert a string value to a specified type.

    If typeName is None, it will attempt to infer the type (bool, int, float, str).

    Args:
        value (str): The string value to convert.
        typeName (Optional[str]): The target type as a string. Supported types are
                                  "bool", "int", "float", "str". If None, type will be inferred.

    Returns:
        Any: The converted value in the specified or inferred type.

    Raises:
        ValueError: If the conversion fails for the specified type.
    """
    if typeName:
        t = TYPE_ALIASES.get(typeName.lower())
        if t in CASTERS:
            try:
                return CASTERS[t](value)
            except Exception as e:
                raise ValueError(f"Could not convert '{value}' to {t}: {e}") from e
        # Unknown type -> fall back to inference
    # Inference: bool -> int -> float -> str
    try:
        return _parse_bool(value)
    except ValueError:
        pass
    try:
        return int(str(value).strip())
    except ValueError:
        pass
    try:
        return float(str(value).strip())
    except ValueError:
        return value

def _prompt_for_value(key: str, typeName: Optional[str] = None, default: Optional[str] = None, prompt: Optional[str] = None) -> Any:
    """Prompt the user for a value for a given key.

    If a default value is provided, it will be shown in the prompt. In that case,
    if the user presses Enter without typing anything, the default value will be used.

    Args:
        key (str): The key for which the value is being requested.
        prompt (Optional[str]): Custom prompt message. Can use {default} placeholder.
        default (Optional[str]): Default value to use if the user does not provide input.
        description (Optional[str]): Description of the key to be printed before the prompt.

    Returns:
        Any: The value provided by the user (converted to python type) or the default value if applicable.
    """
    if not prompt:
        prompt = f'Enter value for "{key}"' + (f' [default={default}]' if default is not None else '') + ': '
    else:
        # Inject default value into custom prompt string using {default} placeholder
        prompt = prompt.format(default=default if default is not None else '')
        if not prompt.endswith(': '):
            prompt += ': '

    try:
        value = input(prompt)
    except EOFError:
        # Handle non-interactive environments by returning default or empty string
        value = ""

    if value == "" and default is not None:
        return default
    return _cast_value(value, typeName)

def _get_project_root() -> str:
    """Returns the absolute path to the project root."""
    # This file is in lib/config.py, so root is parent of parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _find_config_files() -> list[str]:
    """Finds all config.yaml files in core, plugins, and root, sorted by depth (deepest first)."""
    root = _get_project_root()
    patterns = [
        os.path.join(root, "core", "**", CONFIG_FILE),
        os.path.join(root, "plugins", "**", CONFIG_FILE),
        # Also direct children of core/plugins in case glob behavior varies
        os.path.join(root, "core", CONFIG_FILE),
        os.path.join(root, "plugins", CONFIG_FILE),
        os.path.join(root, CONFIG_FILE)
    ]

    found_files: list[str] = []
    for p in patterns:
        found_files.extend(glob.glob(p, recursive=True))

    # Deduplicate and sort by depth descending (deepest first)
    # Deeper files are loaded first, then overwritten by shallower files (higher in tree)
    unique_files = list(set(os.path.abspath(f) for f in found_files))
    unique_files.sort(key=lambda f: f.count(os.sep), reverse=True)
    return unique_files

def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> None:
    """Recursively merge update dict into base dict. Returns nothing, modifies base in place."""
    for k, v in update.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v

def _load_and_merge_configs() -> Dict[str, Any]:
    """Loads all found configs and merges them sequentially."""
    files = _find_config_files()
    final_config: Dict[str, Any] = {}

    # Iterate from deepest to shallowest
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                # Shallow files override deep files, so we merge INTO the existing structure
                # (which starts empty, then gets deep content, then gets shallow content)
                # Wait: if we process deepest first, then `final_config` has deep content.
                # Then we process shallow. Shallow content should OVERRIDE.
                # `_deep_merge(base, update)`: update overrides base.
                # So we want `base` to be the accumulated config (from deep), and `update` to be current shallow config?
                # YES.
                # Example:
                # 1. Deep file: {a: 1} -> final_config = {a: 1}
                # 2. Shallow file: {a: 2} -> _deep_merge({a: 1}, {a: 2}) -> final_config = {a: 2}
                # Correct.
                _deep_merge(final_config, data)
        except Exception as e:
            print(f"Warning: Failed to load config file {fpath}: {e}")

    return final_config

def load_config(operation: str, requiredConfigs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load merged YAML configuration for one operation section.

    Additional info (multi-line): this function only reads and returns values
    from config files. It does not prompt users and does not inject schema
    metadata into returned values.

    Args:
        operation (str): Section name to load from YAML hierarchy.
        requiredConfigs (Dict[str, Any], optional): Unused compatibility
            parameter retained for legacy callers.

    Returns:
        Dict[str, Any]: Values found under the operation section.
    """
    _ = requiredConfigs
    configPars = _load_and_merge_configs()
    opConfig = configPars.get(operation, {})
    if isinstance(opConfig, dict):
        return opConfig.copy()
    return {}


def _with_schema_defaults(requiredConfigs: Dict[str, Any], configValues: Dict[str, Any]) -> Dict[str, Any]:
    """Apply non-None schema defaults to missing keys.

    Args:
        requiredConfigs (Dict[str, Any]): Schema metadata by key.
        configValues (Dict[str, Any]): Existing config values.

    Returns:
        Dict[str, Any]: New config dict with schema defaults applied.
    """
    resolvedConfig = configValues.copy()

    for key, schema in requiredConfigs.items():
        if key in resolvedConfig:
            continue

        defaultValue = schema.get('default')
        if defaultValue is not None:
            resolvedConfig[key] = defaultValue

    return resolvedConfig


def get_missing_required_keys(requiredConfigs: Dict[str, Any], configValues: Dict[str, Any]) -> list[str]:
    """Return required keys that still need user input.

    Args:
        requiredConfigs (Dict[str, Any]): Schema metadata by key.
        configValues (Dict[str, Any]): Current resolved values.

    Returns:
        list[str]: Required keys that are unresolved.
    """
    missingKeys: list[str] = []

    for key in requiredConfigs:
        if key not in configValues:
            missingKeys.append(key)
            continue

        value = configValues.get(key)
        if isinstance(value, str) and value == '':
            missingKeys.append(key)

    return missingKeys


def resolve_config_values(operation: str, requiredConfigs: Dict[str, Any],
                          overrides: Dict[str, Any] | None = None) -> tuple[Dict[str, Any], list[str]]:
    """Resolve operation config values without prompting.

    Additional info (multi-line): this function is intended for pre-mount
    planning. It merges YAML values with optional programmatic overrides,
    applies static schema defaults, and reports unresolved required keys.

    Args:
        operation (str): Section name in config.yaml.
        requiredConfigs (Dict[str, Any]): Schema dict for the operation.
        overrides (Dict[str, Any] | None): Optional in-memory overrides.

    Returns:
        tuple[Dict[str, Any], list[str]]: Resolved values and unresolved required keys.
    """
    configValues = load_config(operation)

    if overrides:
        configValues.update(overrides)

    resolvedValues = _with_schema_defaults(requiredConfigs, configValues)
    missingKeys = get_missing_required_keys(requiredConfigs, resolvedValues)
    return resolvedValues, missingKeys

def _prompt_secure(key: str, prompt: str | None, required: bool, default: str | None = None) -> str:
    """Prompt for secure input (password) using getpass with confirmation.

    Additional info (multi-line): prompts the user twice to enter the password
    and validates that both entries match. This prevents typos from being locked in.

    Args:
        key (str): The key name (for error messages).
        prompt (str | None): Custom prompt message. Can use {default} placeholder.
        required (bool): Whether the value is required.
        default (str | None): Default value (for prompt display only, not recommended for passwords).

    Returns:
        str: The password entered by the user.
    """
    import getpass

    if not prompt:
        prompt = f'Enter {key}'
    else:
        # Inject default value into custom prompt string using {default} placeholder
        prompt = prompt.format(default=default if default is not None else '')

    if not prompt.endswith(': '):
        prompt += ': '

    confirmPrompt = f'Confirm {key}: '

    while True:
        value = getpass.getpass(prompt)

        # If not required and user pressed Enter, allow empty
        if not value and not required:
            return value

        # If required and empty, error and retry
        if not value and required:
            print(f"Error: {key} is required.")
            continue

        # Ask for confirmation
        confirm = getpass.getpass(confirmPrompt)

        # Check if they match
        if value == confirm:
            return value

        print("Error: Passwords do not match. Please try again.")


def validate_and_prompt(requiredConfigs: Dict[str, Any], existingConfig: Dict[str, Any],
                        keysToPrompt: list[str] | None = None,
                        defaultOverrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Validate config and prompt for missing required values.

    Additional info (multi-line): by default this prompts unresolved required
    keys. Callers can pass a specific key list and optional per-key dynamic
    defaults (for example values read from a mounted target OS).

    Args:
        requiredConfigs (Dict[str, Any]): Schema defining required configs.
        existingConfig (Dict[str, Any]): Already loaded/provided configs.
        keysToPrompt (list[str] | None): Optional explicit keys to prompt.
        defaultOverrides (Dict[str, Any] | None): Optional per-key runtime defaults.

    Returns:
        Dict[str, Any]: Complete validated config dict.
    """
    finalConfig = _with_schema_defaults(requiredConfigs, existingConfig)
    dynamicDefaults = defaultOverrides or {}

    keysToProcess = keysToPrompt if keysToPrompt is not None else get_missing_required_keys(requiredConfigs, finalConfig)

    for key in keysToProcess:
        schema = requiredConfigs.get(key)
        if not schema:
            continue

        # Get schema metadata
        typeName = schema.get('type', 'str')
        default = dynamicDefaults.get(key, schema.get('default'))
        prompt = schema.get('prompt')
        secure = schema.get('secure', False)

        # Keys selected for prompting are required for completion.
        required = True

        # Prompt user
        if secure:
            value = _prompt_secure(key, prompt, required, default)
        else:
            while True:
                value = _prompt_for_value(key, typeName, default, prompt)
                if required and value == '':
                    print(f"Error: {key} is required.")
                    continue
                break

        finalConfig[key] = value

    return finalConfig


def load_and_validate_config(operation: str, requiredConfigs: Dict[str, Any],
                             overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Load configuration from YAML hierarchy and validate/prompt for missing values.

    Additional info (multi-line): this is the main entry point for modules to get
    their complete configuration. It loads from the YAML hierarchy, applies any
    programmatic overrides, and prompts for missing required values.

    Args:
        operation (str): Section name in config.yaml (e.g., 'hostname', 'network').
        requiredConfigs (Dict[str, Any]): Schema dict defining what configs are needed.
        overrides (Dict[str, Any] | None): Optional programmatic overrides (for tests/CLI args).

    Returns:
        Dict[str, Any]: Complete validated configuration dict.

    Example:
        REQUIRED_CONFIGS = {
            'hostname': {'type': 'str', 'prompt': 'Enter hostname'},
            'password': {'type': 'str', 'prompt': 'Enter password', 'secure': True}
        }

        configs = load_and_validate_config('hostname', REQUIRED_CONFIGS)
    """
    resolvedConfig, missingKeys = resolve_config_values(operation, requiredConfigs, overrides=overrides)
    return validate_and_prompt(requiredConfigs, resolvedConfig, keysToPrompt=missingKeys)


def get_config_value(configs: Optional[Dict[str, Any]], key: str, default: Any) -> Any:
    """Get a configuration value for a specific key.

    Args:
        configs (Optional[Dict[str, Any]]): The configuration dictionary.
        key (str): The key for which the value is being requested.
        default (Any): Default value to return if the key is not found.

    If configs is None or does not contain the key, it will return the default value,
    else it will return the value from the configs dictionary.

    Returns:
        Any: The value for the specified key, either from the config file or the default value.
    """
    if configs:
        return configs.get(key, default)
    else:
        return default

# Example usage:
if __name__ == "__main__":
    config = load_config('serialport')
    print(config)
