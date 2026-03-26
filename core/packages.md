# Packages Module

The `packages.py` module allows you to easily provision additional software packages on your image during the build process, completely avoiding interactive installation prompts.

This module monitors the top-level `packages` YAML tree inside your `config.yaml`.

## Configuration Options

Inside `config.yaml`:

```yaml
packages:
  apt:
    - htop
    - vim
    - i2c-tools
  pip:
    - requests
    - RPi.GPIO
    - paho-mqtt
```

### Supported Keys:

* `apt`: (Optional Array of Strings) A list of Debian/Ubuntu packages to install via `apt-get install -y`.
* `pip`: (Optional Array of Strings) A list of Python packages to install globally. Under the hood, this uses `pip3 install <package> --break-system-packages` to ensure it integrates seamlessly into the global target environment (required for headless Kiosk/Lite images on newer RaspiOS distributions).
