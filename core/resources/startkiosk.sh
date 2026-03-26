#!/bin/bash

# Execute the dimmer script in the background if it is installed and executable
DIMMER_SCRIPT="/home/pi/bin/scripts/startdimmer.sh"
if [[ -x "$DIMMER_SCRIPT" ]]; then
    "$DIMMER_SCRIPT" &
fi

# Launch Chromium, replacing the bash process
exec /usr/bin/chromium-browser http://localhost:80 \
    --kiosk \
    --start-fullscreen \
    --no-sandbox \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --ozone-platform=wayland \
    --user-data-dir=/tmp/chromium-kiosk \
    --disable-session-crashed-bubble \
    --hide-scrollbars \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-gpu-program-cache \
    --disable-extensions \
    --safebrowsing-disable-auto-update \
    --disable-client-side-phishing-detection \
    --check-for-update-interval=1 \
    --simulate-critical-update \
    --incognito \
    --disk-cache-dir=/dev/null \
    --disk-cache-size=1 \
    --enable-features=OverlayScrollbar \
    --start-maximized
