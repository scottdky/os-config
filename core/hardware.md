# Hardware Configuration Module

The `hardware.py` module exposes basic integrations for explicitly switching on board-level features of a Raspberry Pi that are usually disabled by default in headless images.

This module actively monitors the top-level `hardware` YAML tree inside your `config.yaml`.

## Configuration Options

Inside `config.yaml`:

```yaml
hardware:
  spi: true
  i2c: true
  power_toggle: true
```

* `spi`: Enables the SPI interface (`dtparam=spi=on`).
* `i2c`: Enables the standard I2C interface (`dtparam=i2c_arm=on`).
* `power_toggle`: Maps the shutdown overlays directly to specific GPIO headers (enables both `gpio-shutdown` and `i2c1,pins_44_45`).
* `custom_config`: (Optional Array of Strings) A list of exact configuration strings to manually inject or ensure are active within `/boot/firmware/config.txt`.
* `udev`: (Optional Dictionary) Key-value pairs mapping the rule's filename to the raw `udev` rule content. Automatically drops them into `/etc/udev/rules.d/` and forces a reload.

### Advanced Example

```yaml
hardware:
  custom_config:
    - "dtparam=audio=on"
    - "dtoverlay=vc4-kms-v3d"
  udev:
    "99-i2c.rules": |
      SUBSYSTEM=="i2c-dev", MODE="0666"
    "99-usb-serial.rules": |
      SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666"
```
