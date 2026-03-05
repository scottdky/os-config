# OS Config

Multi-location OS management for localhost, remote SSH, and ARM images/SD cards.

## Setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```


## Configuration

This project uses a hierarchical configuration system. `config.yaml` files are automatically discovered and loaded from the following locations:

1.  `config.yaml` in the project root (Highest Priority)
2.  `core/**/config.yaml` (Base Configuration)
3.  `plugins/**/config.yaml` (Plugin Configuration)

Files are loaded in order of depth (deepest first), meaning:
-   A `config.yaml` in the project root will override settings from `core/` or `plugins/`.
-   Files in `core/` or `plugins/` (usually lower in the directory tree) provide defaults.

### Configuration Format

Example `config.yaml`:

```yaml
# Root config.yaml
serialport:
    baudrate: 115200

network:
    wifi_ssid: "MyHomeNetwork"
```

If a key is missing for a selected operation, the script prompts for it at runtime.

```yaml
network:
    wifi_ssid: "MyHomeNetwork"
    # wifi_password omitted -> prompted when network operation runs
```

### Advanced Configuration

*   **Overriding a List:** Lists are replaced, not merged. Redefining a list in a higher-priority file will completely overwrite the deeper one.
    ```yaml
    # If core/config.yaml has:
    # packages: [vim, git]

    # Root config.yaml:
    packages:
        - nano
        - curl
    # Result: packages = [nano, curl]
    ```

*   **Unspecifying a Value (`null`):** Use `null` to explicitly set a value to `None`.
    ```yaml
    rtc:
        addr: null # Disables the address setting, effectively "unsetting" it
    ```

### Overriding Keys

To override a value from a lower-precedence config file, simply define the key in your higher-precedence `config.yaml`.

**Original (core/config.yaml):**
```yaml
network:
    wifi_ssid: "DefaultSSID"
```

**Override (root config.yaml):**
```yaml
network:
    wifi_ssid: "MyHomeNetwork"
    # To set an explicit empty value, use null
    wifi_password: null
```

Result: `wifi_ssid` is "MyHomeNetwork", and `wifi_password` is `None`.
