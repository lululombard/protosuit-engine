#!/usr/bin/env bash
# Super Haxagon Launcher Script
# Launches Super Haxagon on left display and duplicates to right display using ffmpeg

set -e

# Get display config from environment (set by ExecLauncher)
DISPLAY_WIDTH="${PROTOSUIT_DISPLAY_WIDTH:-720}"
DISPLAY_HEIGHT="${PROTOSUIT_DISPLAY_HEIGHT:-720}"
LEFT_X="${PROTOSUIT_LEFT_X:-0}"
RIGHT_X="${PROTOSUIT_RIGHT_X:-720}"
POS_Y="${PROTOSUIT_Y:-0}"
X_DISPLAY="${DISPLAY:-:0}"

echo "[superhaxagon.sh] Starting Super Haxagon launcher"
echo "[superhaxagon.sh] Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"
echo "[superhaxagon.sh] Left: ${LEFT_X},${POS_Y} | Right: ${RIGHT_X},${POS_Y}"

# Super Haxagon executable path
GAME_PATH="/opt/superhaxagon/build/SuperHaxagon"

if [ ! -f "$GAME_PATH" ]; then
    echo "[superhaxagon.sh] ERROR: Super Haxagon not found at $GAME_PATH"
    exit 1
fi

# PID tracking for cleanup
MIRROR_PID=""

# Cleanup function
cleanup() {
    echo "[superhaxagon.sh] Cleaning up..."

    # Kill mirror process
    if [ -n "$MIRROR_PID" ]; then
        kill $MIRROR_PID 2>/dev/null || true
        wait $MIRROR_PID 2>/dev/null || true
    fi

    # Kill game
    pkill -9 SuperHaxagon 2>/dev/null || true

    exit 0
}

trap cleanup SIGTERM SIGINT

# Launch Super Haxagon
echo "[superhaxagon.sh] Launching Super Haxagon..."
cd /opt/superhaxagon/build
$GAME_PATH &
GAME_PID=$!
echo "[superhaxagon.sh] Game started (PID: $GAME_PID)"

# Wait for game window to appear and get window ID
echo "[superhaxagon.sh] Waiting for game window..."
GAME_WINDOW=""
for attempt in {1..30}; do
    # Search by window name instead of PID (more reliable)
    GAME_WINDOW=$(xdotool search --name "SuperHaxagon" 2>/dev/null | head -1 || true)

    if [ -n "$GAME_WINDOW" ]; then
        echo "[superhaxagon.sh] Found game window: $GAME_WINDOW"
        WINDOW_NAME=$(xdotool getwindowname $GAME_WINDOW 2>/dev/null || true)
        echo "[superhaxagon.sh] Window name: $WINDOW_NAME"
        break
    fi

    # Check if process is still alive
    if ! kill -0 $GAME_PID 2>/dev/null; then
        echo "[superhaxagon.sh] ERROR: Game process died during startup"
        exit 1
    fi

    echo "[superhaxagon.sh] Window not found yet (attempt $attempt/30)..."
    sleep 0.5
done

if [ -z "$GAME_WINDOW" ]; then
    echo "[superhaxagon.sh] ERROR: Could not find game window"
    cleanup
    exit 1
fi

# Position and resize game window on left display
echo "[superhaxagon.sh] Positioning and resizing game window..."
xdotool windowmove $GAME_WINDOW $LEFT_X $POS_Y 2>/dev/null || true
xdotool windowsize $GAME_WINDOW $DISPLAY_WIDTH $DISPLAY_HEIGHT 2>/dev/null || true

# Try to make window undecorated/fullscreen if needed
xdotool windowactivate $GAME_WINDOW 2>/dev/null || true

# Set up display duplication using X11 native mirroring
# Capture left display (HDMI-1) and show it on right display (HDMI-2)
echo "[superhaxagon.sh] Setting up screen duplication with X11 mirror..."
echo "[superhaxagon.sh] Capturing from HDMI-1 at ${LEFT_X},${POS_Y}"

# Start X11 mirror (hardware accelerated with OpenGL)
MIRROR_SCRIPT="/home/proto/protosuit-engine/utils/x11_mirror.py"
VENV_PYTHON="/home/proto/protosuit-engine/env/bin/python3"

if [ -f "$MIRROR_SCRIPT" ]; then
    echo "[superhaxagon.sh] Starting OpenGL-accelerated mirror (low CPU usage)"
    if [ -f "$VENV_PYTHON" ]; then
        $VENV_PYTHON "$MIRROR_SCRIPT" $LEFT_X $POS_Y $DISPLAY_WIDTH $DISPLAY_HEIGHT $RIGHT_X $POS_Y &
    else
        python3 "$MIRROR_SCRIPT" $LEFT_X $POS_Y $DISPLAY_WIDTH $DISPLAY_HEIGHT $RIGHT_X $POS_Y &
    fi
    MIRROR_PID=$!
    echo "[superhaxagon.sh] Started OpenGL mirror (PID: $MIRROR_PID)"
else
    echo "[superhaxagon.sh] WARNING: Mirror script not found at $MIRROR_SCRIPT"
fi

if [ -n "$MIRROR_PID" ]; then
    # Give mirror a moment to start
    sleep 1

    # Find and configure the mirror window
    echo "[superhaxagon.sh] Configuring mirror window..."
    MIRROR_WINDOW=$(xdotool search --name "Mirror" 2>/dev/null | head -1 || true)
    if [ -n "$MIRROR_WINDOW" ]; then
        xdotool windowmove $MIRROR_WINDOW $RIGHT_X $POS_Y 2>/dev/null || true
        echo "[superhaxagon.sh] Mirror window positioned at ${RIGHT_X},${POS_Y}"
    fi
fi

# Focus back on the game window so keyboard input goes to the game
echo "[superhaxagon.sh] Focusing game window for keyboard input..."
xdotool windowactivate $GAME_WINDOW 2>/dev/null || true
xdotool windowfocus $GAME_WINDOW 2>/dev/null || true

# Move cursor off-screen permanently (more reliable than unclutter)
echo "[superhaxagon.sh] Hiding cursor by moving it off-screen..."
xdotool mousemove 2000 2000 2>/dev/null || true

echo "[superhaxagon.sh] Super Haxagon is running"
echo "[superhaxagon.sh] Game PID: $GAME_PID"
echo "[superhaxagon.sh] Screen duplication active"
echo "[superhaxagon.sh] Continuously repositioning game window..."

# Function to check if processes are still running
processes_running() {
    kill -0 $GAME_PID 2>/dev/null
}

# Continuously monitor and reposition windows while game is running
while processes_running; do
    sleep 1

    # Reposition and resize game window to keep it on the left display
    xdotool windowmove $GAME_WINDOW $LEFT_X $POS_Y 2>/dev/null || true
    xdotool windowsize $GAME_WINDOW $DISPLAY_WIDTH $DISPLAY_HEIGHT 2>/dev/null || true

    # Also keep the mirror window in position on the right display
    if [ -n "$MIRROR_WINDOW" ]; then
        xdotool windowmove $MIRROR_WINDOW $RIGHT_X $POS_Y 2>/dev/null || true
        xdotool windowsize $MIRROR_WINDOW $DISPLAY_WIDTH $DISPLAY_HEIGHT 2>/dev/null || true
    fi

    # Keep cursor off-screen (in case it reappears)
    xdotool mousemove 2000 2000 2>/dev/null || true
done

echo "[superhaxagon.sh] Game process exited"

cleanup
