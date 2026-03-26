# Kiosk Webserver Implementation Guide

When using the `kiosk` operation, the system is configured to launch a Wayland-based Chromium browser on boot in a restricted UI environment via `cage`. For the browser to have local content to display, a corresponding local webserver is expected to be provisioned.

## Systemd Architecture

The kiosk setup relies on two coordinated systemd services:
1. `webserver.service`: A background service that runs early in the boot process.
2. `kiosk.service`: The UI service (Cage + Chromium), which is hardcoded to wait for the webserver to initialize (`After=multi-user.target graphical.target webserver.service`).

## Implementing the Webserver Plugin

A future plugin must provision the actual webserver codebase and supply the expected startup wrapper.

### 1. The Startup Script Requirement

The newly provisioned `webserver.service` statically expects an executable shell script located at:
`/home/pi/bin/scripts/startwebserver.sh`

Your future plugin/operation should:
1. Create the `/home/pi/bin/scripts` directory if it does not exist.
2. Write the `startwebserver.sh` script inside it.
3. Ensure the file is executable (`chmod +x`).

### 2. Example `startwebserver.sh`

Here is an example of what that script might look like if you were running a Python-based server:

```bash
#!/bin/bash

# Navigate to the webserver project directory
cd /home/pi/my_web_app

# Activate virtual environment if applicable
source .venv/bin/activate

# Start the webserver
exec python3 app.py
```

*Note: Using `exec` at the end ensures the webserver process replaces the bash script, proper systemd signal monitoring, and clean shutdowns.*

### 3. Execution Context & Constraints

- **User Context**: The `startwebserver.sh` script is executed securely as the user `pi`, **not** `root`. This prevents runtime file permission issues and safely allows the script to use `pi`'s local environment or SSH keys.
- **Port 80 Constraint**: By default, `kiosk.service` opens Chromium to `http://localhost:80`. Because the webserver runs as an unprivileged user (`pi`), it cannot bind natively to port `80`. You must handle this in your plugin by implementing one of the following strategies:
  1. **Nginx Reverse Proxy**: Install `nginx` to listen on port 80 and forward requests to your webserver's unprivileged port (e.g., `8080`).
  2. **Port Forwarding**: Add an `iptables` rule to route port `80` traffic to port `8080`.
  3. **Capability Binding**: Use `setcap 'cap_net_bind_service=+ep'` on the webserver binary (like node or python) so it can bind port 80 natively.
  4. **Edit Kiosk URL**: Override the `kiosk.service` inside your plugin to point `chromium-browser` directly to `http://localhost:8080`.
