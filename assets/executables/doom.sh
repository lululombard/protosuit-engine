#!/usr/bin/env bash
# Doom Launcher Script
# Launches Chocolate Doom in 1v1 deathmatch mode on dual displays

set -e

# Signal to launcher that we need extended setup time
mosquitto_pub -t protosuit/launcher/setup -m "started"

# Get display config from environment (set by ExecLauncher)
DISPLAY_WIDTH="${PROTOSUIT_DISPLAY_WIDTH:-720}"
DISPLAY_HEIGHT="${PROTOSUIT_DISPLAY_HEIGHT:-720}"
LEFT_X="${PROTOSUIT_LEFT_X:-0}"
RIGHT_X="${PROTOSUIT_RIGHT_X:-720}"
POS_Y="${PROTOSUIT_DOOM_Y:-90}"

echo "[doom.sh] Starting Doom launcher"
echo "[doom.sh] Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"
echo "[doom.sh] Left: ${LEFT_X},${POS_Y} | Right: ${RIGHT_X},${POS_Y}"

# Doom executable path
DOOM_PATH="/usr/games/chocolate-doom"
CUSTOM_WAD="/usr/share/games/doom/duelpack.wad"

if [ ! -f "$DOOM_PATH" ]; then
    echo "[doom.sh] ERROR: Chocolate Doom not found at $DOOM_PATH"
    exit 1
fi

if [ ! -f "$CUSTOM_WAD" ]; then
    echo "[doom.sh] ERROR: Custom WAD not found at $CUSTOM_WAD"
    echo "[doom.sh] Please run the Ansible playbook to download the WAD"
    exit 1
fi

# Cleanup function
cleanup() {
    echo "[doom.sh] Cleaning up..."
    pkill -9 chocolate-doom 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Create temporary config files with window positions
SERVER_CONFIG="/tmp/doom_server.cfg"
CLIENT_CONFIG="/tmp/doom_client.cfg"

cat > "$SERVER_CONFIG" << EOF
window_position                 "${LEFT_X},${POS_Y}"
key_fire                        30
key_use                         48
EOF

cat > "$CLIENT_CONFIG" << EOF
window_position                 "${RIGHT_X},${POS_Y}"
key_fire                        30
key_use                         48
EOF

echo "[doom.sh] Created config files with window positions"

# Launch server (left display) with custom config
echo "[doom.sh] Launching server at ${LEFT_X},${POS_Y}..."
echo "[doom.sh] ===== SERVER OUTPUT ====="
$DOOM_PATH \
    -config "$SERVER_CONFIG" \
    -width $DISPLAY_WIDTH \
    -height $DISPLAY_HEIGHT \
    -file "$CUSTOM_WAD" \
    -warp 02 \
    -server \
    -deathmatch \
    -nomonsters \
    -privateserver \
    -nodes 2 \
    -window \
    -nograbmouse &

SERVER_PID=$!
echo "[doom.sh] Server started (PID: $SERVER_PID)"
sleep 2

# Launch client (right display) with custom config
echo "[doom.sh] Launching client at ${RIGHT_X},${POS_Y}..."
echo "[doom.sh] ===== CLIENT OUTPUT ====="
$DOOM_PATH \
    -config "$CLIENT_CONFIG" \
    -width $DISPLAY_WIDTH \
    -height $DISPLAY_HEIGHT \
    -file "$CUSTOM_WAD" \
    -connect localhost \
    -nomusic \
    -window \
    -nograbmouse &

CLIENT_PID=$!
echo "[doom.sh] Client started (PID: $CLIENT_PID)"

# Check if both processes are running
sleep 1
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[doom.sh] ERROR: Server process died!"
    exit 1
fi

if ! kill -0 $CLIENT_PID 2>/dev/null; then
    echo "[doom.sh] ERROR: Client process died!"
    exit 1
fi

# Find the windows and position them with xdotool as fallback
echo "[doom.sh] Finding and positioning windows..."
sleep 1

WINDOW_ARRAY=()
for attempt in {1..100}; do
    WINDOWS=$(xdotool search --name "Chocolate Doom" 2>/dev/null || true)
    WINDOW_ARRAY=($WINDOWS)

    if [ ${#WINDOW_ARRAY[@]} -ge 2 ]; then
        echo "[doom.sh] Found ${#WINDOW_ARRAY[@]} windows"
        break
    fi

    echo "[doom.sh] Found ${#WINDOW_ARRAY[@]} window(s), waiting for both... (attempt $attempt/10)"
    sleep 0.1
done

if [ ${#WINDOW_ARRAY[@]} -ge 2 ]; then
    echo "[doom.sh] Positioning server window at ${LEFT_X},${POS_Y}"
    echo "[doom.sh] Positioning client window at ${RIGHT_X},${POS_Y}"
elif [ ${#WINDOW_ARRAY[@]} -eq 1 ]; then
    echo "[doom.sh] WARNING: Only found 1 window, both might be stacked"
else
    echo "[doom.sh] WARNING: No windows found via xdotool"
fi

# Game will auto-start when both players connect (thanks to -nodes 2)
echo "[doom.sh] Doom is running (PIDs: Server=$SERVER_PID, Client=$CLIENT_PID)"
echo "[doom.sh] Continuously repositioning windows to keep them on displays..."

# Function to check if processes are still running
processes_running() {
    kill -0 $SERVER_PID 2>/dev/null || kill -0 $CLIENT_PID 2>/dev/null
}

xdotool windowmove ${WINDOW_ARRAY[0]} $LEFT_X $POS_Y 2>/dev/null || true
xdotool windowmove ${WINDOW_ARRAY[1]} $RIGHT_X $POS_Y 2>/dev/null || true

# Move cursor off-screen permanently (more reliable than unclutter)
echo "[doom.sh] Hiding cursor by moving it off-screen..."
xdotool mousemove 2000 2000 2>/dev/null || true

sleep 1

# Signal to launcher that setup is complete and inputs can be processed
mosquitto_pub -t protosuit/launcher/setup -m "ready"
echo "[doom.sh] Signaled ready for inputs"

# Wait for processes to exit
while processes_running; do
    sleep 1
    # Keep cursor off-screen (in case it reappears)
    xdotool mousemove 2000 2000 2>/dev/null || true
done

echo "[doom.sh] Processes exited"

cleanup
