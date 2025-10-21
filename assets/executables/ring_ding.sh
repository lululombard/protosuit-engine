#!/usr/bin/env bash
# Ring Ding Launcher Script
# Launches Ring Ding circle timing game on dual displays

set -e

# Get display config from environment (set by ExecLauncher)
DISPLAY_WIDTH="${PROTOSUIT_DISPLAY_WIDTH:-720}"
DISPLAY_HEIGHT="${PROTOSUIT_DISPLAY_HEIGHT:-720}"
LEFT_X="${PROTOSUIT_LEFT_X:-0}"
RIGHT_X="${PROTOSUIT_RIGHT_X:-720}"
POS_Y="${PROTOSUIT_Y:-0}"
X_DISPLAY="${DISPLAY:-:0}"

echo "[ring_ding.sh] Starting Ring Ding launcher"
echo "[ring_ding.sh] Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"
echo "[ring_ding.sh] Left: ${LEFT_X},${POS_Y} | Right: ${RIGHT_X},${POS_Y}"

# Ring Ding executable path
GAME_PATH="/home/proto/protosuit-engine/launcher/games/ring_ding.py"
VENV_PYTHON="/home/proto/protosuit-engine/env/bin/python3"

if [ ! -f "$GAME_PATH" ]; then
    echo "[ring_ding.sh] ERROR: Ring Ding not found at $GAME_PATH"
    exit 1
fi

# Cleanup function
cleanup() {
    echo "[ring_ding.sh] Cleaning up..."
    pkill -9 -f "ring_ding.py" 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Launch Ring Ding
echo "[ring_ding.sh] Launching Ring Ding..."
export DISPLAY=$X_DISPLAY
export PROTOSUIT_DISPLAY_WIDTH=$DISPLAY_WIDTH
export PROTOSUIT_DISPLAY_HEIGHT=$DISPLAY_HEIGHT

if [ -f "$VENV_PYTHON" ]; then
    echo "[ring_ding.sh] Using venv Python: $VENV_PYTHON"
    $VENV_PYTHON "$GAME_PATH" &
else
    echo "[ring_ding.sh] Using system Python"
    python3 "$GAME_PATH" &
fi

GAME_PID=$!
echo "[ring_ding.sh] Game started (PID: $GAME_PID)"

# Move cursor off-screen permanently (more reliable than unclutter)
echo "[ring_ding.sh] Hiding cursor by moving it off-screen..."
xdotool mousemove 2000 2000 2>/dev/null || true

echo "[ring_ding.sh] Ring Ding is running (PID: $GAME_PID)"
echo "[ring_ding.sh] Window positioned at 0,0 via SDL"

# Wait for process to exit
wait $GAME_PID

echo "[ring_ding.sh] Game process exited"

cleanup
