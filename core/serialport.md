## Raspberry Pi Serial & UART Configuration Guide

Configuring the serial ports on a Raspberry Pi is notoriously complex due to hardware limitations across different models (like the Pi 3, Zero W, and Pi 4) and how those ports intersect with the onboard Bluetooth module.

This document serves to clarify the options available, their hardware ramifications, and why the `serialport` operation behaves the way it does.

---

### Understanding the Two UARTs

Most Raspberry Pis feature two types of Universal Asynchronous Receiver-Transmitters (UARTs):

1. **PL011 (Primary, Full UART)**
   - High performance, stable baud rates.
   - Independent of the VPU (Video Processing Unit) clock.
   - Features full hardware flow control and parity.

2. **Mini-UART (Secondary)**
   - Lower performance.
   - Tied directly to the system (VPU) clock. If the Pi throttles down to save power, the baud rate shifts, heavily corrupting communication unless specifically accounted for.
   - No hardware parity support.

### The Bluetooth Conflict

By default, the Pi allocates the high-performance **PL011 UART** to drive the onboard **Bluetooth** module. The weaker **Mini-UART** is routed to the GPIO pins (TXD/RXD on pins 14/15) for use as a Linux console.

If you are using the serial port (via GPIO) to interface with external hardware (like sensors, microcontrollers, or precise timing devices), the Mini-UART's fluctuating speeds will cause significant data drops. You generally need to reclaim the PL011 UART for your GPIO pins.

---

### Configuration Strategy

Our `serialport` module controls this mapping via the device tree (`/boot/config.txt`) using the following settings matrix:

#### 1. Hardware Pin Access (`enable_uart`)
*   **`True`**: Turns on the primary serial port (`/dev/serial0`). It automatically sets the core clock frequency to 250MHz to stabilize the Mini-UART if it is currently mapped to GPIO.
*   **`False`**: Fully shuts down GPIO serial access.

#### 2. Reclaiming the PL011 (`bluetooth`)
If `enable_uart` is True, you must decide how to handle Bluetooth.

*   **`True` (Bluetooth remains on / PL011 mapped to Mini-UART)**
    *   **Action**: Sets `dtoverlay=miniuart-bt` in `config.txt`.
    *   **Result**: Bluetooth stays alive but is forced onto the weaker Mini-UART. This limits Bluetooth bandwidth.
    *   **Advantage**: Reclaims the high-performance PL011 UART for your GPIO pins (`/dev/serial0`) for precision physical hardware communication.

*   **`False` (Disable Bluetooth entirely)** *(Default Recommendation)*
    *   **Action**: Sets `dtoverlay=disable-bt` and masks the `hciuart` systemd service.
    *   **Result**: Bluetooth is completely shut down. The PL011 UART is cleanly mapped to GPIO pins (`/dev/serial0`).
    *   **Advantage**: Most stable configuration, frees up resources, leaves the system clock alone, and prevents Bluetooth-UART buffer collisions entirely.

#### 3. Linux Kernel Shell (`console`)
By default, Raspberry Pi OS attaches a shell (Linux console) to the primary serial port so you can log in without a monitor using a serial cable.

*   **`True`**: Leaves `console=serial0,115200` in `/boot/cmdline.txt`. If you hook external hardware to the RX/TX pins, the hardware will receive Linux boot logs and a login prompt, which will crash most microcontroller software.
*   **`False`**: Removes `console=serial0` from `/boot/cmdline.txt`. The UART is perfectly silent and available as a raw data pipe for your application.

---

### Why We Bypass `raspi-config`

The native `raspi-config` script is conventionally used for interacting with the Pi's state. However, we bypass it for this operation because:
1. `raspi-config` strictly flips `enable_uart=1` and `console=serial0`.
2. It entirely lacks functions, variables, or awareness of the Bluetooth overlay toggles (`disable-bt`, `miniuart-bt`) required to safely switch the PL011 back to GPIO pins.
3. Managing state across both toolsets results in opaque race conditions. Thus, this python module uses the device tree as its single source of truth.
