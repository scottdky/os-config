# Custom Files Module

The `custom_files.py` module replaces interactive prompts by allowing administrators to provision scripts, environments, and `systemd` services at build time completely contained inside `config.yaml`.

## Usage & Properties

Instead of injecting the script during runtime or maintaining arbitrary C-wrapper installers in the toolchain, describe your required configurations locally in the `custom_files` list:

```yaml
custom_files:
  files:
    # Example 1: Basic Inline Content (Usually configs/INI)
    - target: /etc/my-custom-config.conf
      content: |-
        [Settings]
        Mode=Dark
        Timeout=60
      executable: false

    # Example 2: Providing a local filesystem source mapping (Ideal for big binaries/scripts)
    - target: /opt/my_scripts/large_script.sh
      local_source: ./files/large_script.sh
      executable: true

    # Example 3: Full systemd automatic bootstrap
    - target: /etc/systemd/system/my-service.service
      content: |-
        [Unit]
        Description=My Custom Service

        [Service]
        ExecStart=/opt/my_scripts/large_script.sh
        Restart=always

        [Install]
        WantedBy=multi-user.target
      enable_service: true
```

### Supported Keys:
- `target`: (Required String) The destination absolute path on the target OS image.
- `content`: (Optional String) Multi-line string literal representing the file contents.
- `local_source`: (Optional String) A path on your **host machine** to copy from rather than string-lining it here. Note: Provide `content` OR `local_source`, not both.
- `executable`: (Optional Bool) Whether to assign `+x` privileges to the file after it lands.
- `enable_service`: (Optional Bool) When `target` is a `.service` file, automatically reload systemd daemon and calls `systemctl enable` on the file's basename.
