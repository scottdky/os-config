#!/usr/bin/env python3

""" Utilities for managing configurations needed for various operations.

With these utilities, operations can load configurations from a YAML file,
or if they are not specified, they will prompt the user for input.

This can be extra useful for scripts that implement multiple operations
for a specified setup, without needed to prompt the user later on in the
process. It also eliminates the need to prompt the user at all for
most settings.

The YAML file should be structured as follows:

# config.yaml

serialport:
    enable_uart: True
    baudrate: Ask      # Will prompt user if "Ask"
    device: /dev/ttyS0
    add_user_to_dialout: True
    # flow_control: True

network:
    wifi_ssid: Ask
    wifi_password: Ask
    dhcp: True

When a user should be prompted, the value should be set to "Ask".
Alternatively, an operation can specify a set of required keys
and if a key is not found, it will prompt the user for the setting
for that key. In the example above, the key 'flow_control' is commented out,
so the user will be prompted for it if the operation specifies it as a required key.
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
    """Load configuration for a specific operation from config files.

    If a key is set to "Ask" or if it is not found, the user will be prompted
    for the value. If requiredKeys are specified, it will also prompt for those keys
    if they are not found in the operation's configuration.

    Args:
        operation (str): Section of the config to load.
        requiredConfigs (Dict[str, Any], optional): Keys that must be present. Defaults to None.

    Returns:
        Dict[str, Any]: The final configuration dictionary.
    """
    configPars = _load_and_merge_configs()
    opConfig = configPars.get(operation, {})
    finalConfig = {}
    for key, value in opConfig.items():
        if isinstance(value, dict):
            askFlag = bool(value.get('ask', False))
            typeName = value.get('type', None)
            default = value.get('default', None)
            prompt = value.get('prompt', None)
        else:
            askFlag = False
            typeName = None
            default = value
            prompt = None

        if (isinstance(value, str) and value.lower() == "ask") or askFlag:
            while True:
                try:
                    finalConfig[key] = _prompt_for_value(key, typeName, default, prompt)
                    break
                except ValueError as e:
                    print(f"Error: {e}. Please try again.")
        else:
            finalConfig[key] = default

    # Prompt for any missing keys (optional)
    if requiredConfigs:
        for key, default in requiredConfigs.items():
            if key not in finalConfig:
                #finalConfig[key] = _prompt_for_value(key, None, default)
                finalConfig[key] = default
    return finalConfig

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


def validate_and_prompt(requiredConfigs: Dict[str, Any], existingConfig: Dict[str, Any]) -> Dict[str, Any]:
    """Validate config and prompt for missing required values.

    Args:
        requiredConfigs (Dict[str, Any]): Schema defining required configs.
        existingConfig (Dict[str, Any]): Already loaded/provided configs.

    Returns:
        Dict[str, Any]: Complete validated config dict.
    """
    finalConfig = existingConfig.copy()

    for key, schema in requiredConfigs.items():
        # Skip if already have value (and it's not 'Ask')
        currentValue = finalConfig.get(key)
        if currentValue is not None and currentValue != '' and str(currentValue).lower() != 'ask':
            continue

        # Get schema metadata
        typeName = schema.get('type', 'str')
        default = schema.get('default')
        prompt = schema.get('prompt')
        secure = schema.get('secure', False)

        # Determine if required (None default means required)
        required = (default is None)

        # Prompt user
        if secure:
            value = _prompt_secure(key, prompt, required, default)
        else:
            value = _prompt_for_value(key, typeName, default, prompt)

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
            'hostname': {'type': 'str', 'prompt': 'Enter hostname', 'default': None},
            'password': {'type': 'str', 'prompt': 'Enter password', 'secure': True}
        }

        configs = load_and_validate_config('hostname', REQUIRED_CONFIGS)
    """
    # Load from YAML hierarchy (already handles all file merging)
    yamlConfig = load_config(operation, requiredConfigs)

    # Apply programmatic overrides if provided (for tests, CLI args, etc.)
    if overrides:
        yamlConfig.update(overrides)

    # Validate and prompt for any missing required values
    finalConfig = validate_and_prompt(requiredConfigs, yamlConfig)

    return finalConfig


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
