# Kiosk Webserver Implementation Guide

When using the `kiosk` operation, the system is configured to launch a Wayland-based Chromium browser on boot in a restricted UI environment via `cage`. For the browser to have local content to display, a corresponding local webserver is expected to be provisioned.

## Decoupled Architecture

The kiosk setup operates independently of the webserver. When the interface (`kiosk.service`) boots, it initially displays a local HTML loading screen (`loading.html`) rather than pointing directly to `http://localhost`.

This loading screen runs a JavaScript polling loop that continuously checks `http://localhost` for a response. Once the local webserver binds to port 80 and returns a successful response, the browser seamlessly redirects to the actual web application.

### Customizing the Loading Screen

You can configure the style of the `loading.html` page using the `kiosk` properties in your `config.yaml`:

```yaml
kiosk:
  loading_style: "spinner" # Options: black, spinner, text
  loading_text: "System Starting..." # Only used if loading_style is 'text'
```

If these keys are missing, the interactive installer will prompt you to select your preferred loading style.

## Implementing the Webserver Plugin

A future plugin must provision the actual webserver codebase, manage its dependencies, and configure its own systemd service. The `kiosk` operation no longer manages a shared `webserver.service`.

### 1. The Webserver Service

Your plugin should create and install its own unique systemd unit (e.g., `my-web-app.service`) that runs early in the boot process. You do not need to link it functionally to `kiosk.service` because Chromium will patiently wait on the local loading screen until your service comes online.

### 2. Execution Context & Constraints

- **User Context**: It is recommended that your custom service executes securely as the user `pi`, **not** `root`. This prevents runtime file permission issues and safely allows the script to use `pi`'s local environment or SSH keys.
- **Port 80 Constraint**: By default, the Kiosk UI redirects to `http://localhost:80`. Because the webserver runs as an unprivileged user (`pi`), it cannot bind natively to port `80`. You must handle this in your plugin by implementing one of the following strategies:
  1. **Nginx Reverse Proxy**: Install `nginx` to listen on port 80 and forward requests to your webserver's unprivileged port (e.g., `8080`).
  2. **Port Forwarding**: Add an `iptables` rule to route port `80` traffic to port `8080`.
  3. **Capability Binding**: Use `setcap 'cap_net_bind_service=+ep'` on the webserver binary (like node or python) so it can bind port 80 natively.
