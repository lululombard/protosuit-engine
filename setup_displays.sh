#!/bin/bash
# Setup script for dual display Protogen fins

echo "=== Protogen Fin Display Setup ==="
echo ""

# Check if X is installed
if ! command -v startx &> /dev/null; then
    echo "Installing X11..."
    sudo apt install -y xorg x11-xserver-utils
fi

# Create minimal xinitrc for dual displays
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
# Disable screen blanking and power management
xset s off
xset -dpms
xset s noblank

# Allow local connections to X server (needed for fin display manager)
xhost +local:

# Set up dual displays (adjust HDMI port names as needed)
# Use xrandr to configure your specific setup
# Example:
DISPLAY=:0 xrandr --output HDMI-1 --mode 720x720 --pos 0x0 --rotate right
DISPLAY=:0 xrandr --output HDMI-2 --mode 720x720 --pos 720x0 --rotate left

# Keep X running
exec sleep infinity
EOF
chmod +x ~/.xinitrc

echo ""
echo "✓ Created ~/.xinitrc for dual display setup"
echo ""
echo "Next steps:"
echo "1. Start X server: startx"
echo "2. In another terminal, check displays: DISPLAY=:0 xrandr"
echo "3. Configure display positions if needed"
echo "4. Run your Python script: env/bin/python test.py"
echo ""
echo "For automatic startup on boot, you can add to /etc/rc.local:"
echo "  su - proto -c 'startx' &"
