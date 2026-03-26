#!/bin/bash

# Start the Wayland idle manager to dim the screen when not touched.
# Will dim down to a low brightness value, and pop back to 100% on touch.
exec swayidle -w \
    timeout 300 'brightnessctl set 15' \
    resume 'brightnessctl set 100%'
