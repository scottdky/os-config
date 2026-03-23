#!/bin/bash
# First-boot script to install and register the Plymouth Splashscreen
set -e

echo "Starting Plymouth Splashscreen initialization..."
export DEBIAN_FRONTEND=noninteractive

# Update and install tools
apt-get update
apt-get install -y plymouth plymouth-themes

# Register plymouth alternative themes
THEME_DIR="/usr/share/plymouth/themes/custom-splash"

if [ -f "$THEME_DIR/custom-splash.plymouth" ]; then
    update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth "$THEME_DIR/custom-splash.plymouth" 100
    update-alternatives --set default.plymouth "$THEME_DIR/custom-splash.plymouth"

    echo "Rebuilding initramfs..."
    update-initramfs -u
else
    echo "Plymouth theme files not found in $THEME_DIR"
fi

# Clean up / self-disable
systemctl disable splashscreen_install.service || true
rm -f /usr/local/bin/splashscreen_install.sh
rm -f /etc/systemd/system/splashscreen_install.service
systemctl daemon-reload

echo "Plymouth Splashscreen installation completed."
exit 0
