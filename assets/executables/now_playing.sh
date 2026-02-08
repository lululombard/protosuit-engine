#!/usr/bin/env bash
# Now Playing Launcher Script
# Launches Now Playing display on dual displays

set -e

# Get display config from environment (set by ExecLauncher)
DISPLAY_WIDTH="${PROTOSUIT_DISPLAY_WIDTH:-720}"
DISPLAY_HEIGHT="${PROTOSUIT_DISPLAY_HEIGHT:-720}"
LEFT_X="${PROTOSUIT_LEFT_X:-0}"
RIGHT_X="${PROTOSUIT_RIGHT_X:-720}"
POS_Y="${PROTOSUIT_Y:-0}"
X_DISPLAY="${DISPLAY:-:0}"
ACCENT_COLOR="${ACCENT_COLOR:-255,165,0}"

echo "[now_playing.sh] Starting Now Playing launcher"
echo "[now_playing.sh] Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"

# Paths
GAME_PATH="/home/proto/protosuit-engine/launcher/games/now_playing.py"
VENV_PYTHON="/home/proto/protosuit-engine/env/bin/python3"

if [ ! -f "$GAME_PATH" ]; then
    echo "[now_playing.sh] ERROR: now_playing.py not found at $GAME_PATH"
    exit 1
fi

# Cleanup function
cleanup() {
    echo "[now_playing.sh] Cleaning up..."
    pkill -9 -f "now_playing.py" 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Launch
echo "[now_playing.sh] Launching Now Playing..."
export DISPLAY=$X_DISPLAY
export PROTOSUIT_DISPLAY_WIDTH=$DISPLAY_WIDTH
export PROTOSUIT_DISPLAY_HEIGHT=$DISPLAY_HEIGHT
export PROTOSUIT_ACCENT_COLOR=$ACCENT_COLOR

if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON "$GAME_PATH" &
else
    python3 "$GAME_PATH" &
fi

GAME_PID=$!
echo "[now_playing.sh] Started (PID: $GAME_PID)"

# Hide cursor
xdotool mousemove 2000 2000 2>/dev/null || true

# Wait for process to exit
wait $GAME_PID

echo "[now_playing.sh] Process exited"
cleanup
