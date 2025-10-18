#!/usr/bin/env bash
# Doom Launcher Script
# Launches Chocolate Doom in 1v1 deathmatch mode on dual displays

set -e

# Get display config from environment (set by ExecLauncher)
DISPLAY_WIDTH="${PROTOSUIT_DISPLAY_WIDTH:-720}"
DISPLAY_HEIGHT="${PROTOSUIT_DISPLAY_HEIGHT:-720}"
LEFT_X="${PROTOSUIT_LEFT_X:-0}"
RIGHT_X="${PROTOSUIT_RIGHT_X:-720}"
POS_Y="${PROTOSUIT_Y:-0}"

echo "[doom.sh] Starting Doom launcher"
echo "[doom.sh] Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"
echo "[doom.sh] Left: ${LEFT_X},${POS_Y} | Right: ${RIGHT_X},${POS_Y}"

# Doom executable path
DOOM_PATH="/usr/games/chocolate-doom"

if [ ! -f "$DOOM_PATH" ]; then
    echo "[doom.sh] ERROR: Chocolate Doom not found at $DOOM_PATH"
    exit 1
fi

# Cleanup function
cleanup() {
    echo "[doom.sh] Cleaning up..."
    pkill -9 chocolate-doom 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Launch server (left display)
echo "[doom.sh] Launching server..."
$DOOM_PATH \
    -width $DISPLAY_WIDTH \
    -height $DISPLAY_HEIGHT \
    -server \
    -deathmatch \
    -nosound \
    -window \
    -nograbmouse \
    >/dev/null 2>&1 &

SERVER_PID=$!
sleep 0.1

# Launch client (right display)
echo "[doom.sh] Launching client..."
$DOOM_PATH \
    -width $DISPLAY_WIDTH \
    -height $DISPLAY_HEIGHT \
    -connect localhost \
    -nosound \
    -window \
    -nograbmouse \
    >/dev/null 2>&1 &

CLIENT_PID=$!
sleep 0.2

# Find and position windows
echo "[doom.sh] Positioning windows..."
WINDOWS=$(xdotool search --name "Chocolate Doom" 2>/dev/null || true)
WINDOW_ARRAY=($WINDOWS)

if [ ${#WINDOW_ARRAY[@]} -ge 2 ]; then
    # Position server window (left)
    xdotool windowmove ${WINDOW_ARRAY[0]} $LEFT_X $POS_Y
    xdotool windowsize ${WINDOW_ARRAY[0]} $DISPLAY_WIDTH $DISPLAY_HEIGHT
    echo "[doom.sh] Positioned server window ${WINDOW_ARRAY[0]} at ${LEFT_X},${POS_Y}"

    # Position client window (right)
    xdotool windowmove ${WINDOW_ARRAY[1]} $RIGHT_X $POS_Y
    xdotool windowsize ${WINDOW_ARRAY[1]} $DISPLAY_WIDTH $DISPLAY_HEIGHT
    echo "[doom.sh] Positioned client window ${WINDOW_ARRAY[1]} at ${RIGHT_X},${POS_Y}"
elif [ ${#WINDOW_ARRAY[@]} -eq 1 ]; then
    # Only one window found, position on left
    xdotool windowmove ${WINDOW_ARRAY[0]} $LEFT_X $POS_Y
    xdotool windowsize ${WINDOW_ARRAY[0]} $DISPLAY_WIDTH $DISPLAY_HEIGHT
    echo "[doom.sh] Positioned single window ${WINDOW_ARRAY[0]} at ${LEFT_X},${POS_Y}"
fi

# Auto-start game by sending Space to server
echo "[doom.sh] Auto-starting game..."
sleep 2
if [ ${#WINDOW_ARRAY[@]} -ge 1 ]; then
    xdotool windowactivate --sync ${WINDOW_ARRAY[0]}
    sleep 0.5
    xdotool key --window ${WINDOW_ARRAY[0]} space
    echo "[doom.sh] Sent Space to server window"
fi

# Keep repositioning windows for stability
echo "[doom.sh] Ensuring windows stay visible..."
for i in {1..10}; do
    sleep 0.5
    if [ ${#WINDOW_ARRAY[@]} -ge 2 ]; then
        xdotool windowmove ${WINDOW_ARRAY[0]} $LEFT_X $POS_Y 2>/dev/null || true
        xdotool windowmove ${WINDOW_ARRAY[1]} $RIGHT_X $POS_Y 2>/dev/null || true
    fi
done

# Wait for processes to exit
echo "[doom.sh] Doom is running (PIDs: $SERVER_PID, $CLIENT_PID)"
wait $SERVER_PID $CLIENT_PID 2>/dev/null || true

cleanup
