#!/usr/bin/env bash
# Test script for MQTT input handling across all games
# Tests Doom (multi-window), Super Haxagon (single-window), and Ring Ding (single-window)

set -e

echo "=========================================="
echo "MQTT Input Test Script"
echo "=========================================="
echo ""

# Restart launcher
echo "[1/3] Restarting launcher..."
sudo systemctl restart protosuit-launcher
sleep 2
echo "✓ Launcher restarted"
echo ""

# Test 1: Doom (multi-window game with window targeting)
echo "=========================================="
echo "TEST 1: Doom (Multi-Window)"
echo "=========================================="
echo "Starting Doom..."
mosquitto_pub -t "protogen/fins/launcher/start/exec" -m 'doom.sh'
sleep 6

echo "Releasing all directional keys..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keyup", "display": "right"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keyup", "display": "left"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keyup", "display": "right"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keyup", "display": "left"}'
sleep 0.5

echo "Testing independent controls: right player turns right, left player turns left..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keydown", "display": "right"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keydown", "display": "left"}'
sleep 5

echo "Releasing all keys..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keyup", "display": "right"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keyup", "display": "left"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keyup", "display": "right"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keyup", "display": "left"}'
sleep 1

echo "✓ Doom test complete (players should have turned independently)"
echo ""

# Test 2: Super Haxagon (single-window game with focused window mode)
echo "=========================================="
echo "TEST 2: Super Haxagon (Single-Window)"
echo "=========================================="
echo "Starting Super Haxagon..."
mosquitto_pub -t "protogen/fins/launcher/start/exec" -m 'superhaxagon.sh'
sleep 6

echo "Pressing Return to start..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Return", "action": "keydown", "display": "left"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Return", "action": "keyup", "display": "left"}'
sleep 1

echo "Selecting level with Right arrow..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keydown", "display": "left"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Right", "action": "keyup", "display": "left"}'
sleep 1

echo "Starting game with Return..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Return", "action": "keydown", "display": "left"}'
sleep 0.1
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Return", "action": "keyup", "display": "left"}'
sleep 0.5

echo "Holding Left for 3 seconds..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keydown", "display": "left"}'
sleep 3
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "Left", "action": "keyup", "display": "left"}'
sleep 1

echo "✓ Super Haxagon test complete (pointer should have moved left)"
echo ""
sleep 10

# Test 3: Ring Ding (single-window game)
echo "=========================================="
echo "TEST 3: Ring Ding (Single-Window)"
echo "=========================================="
echo "Starting Ring Ding..."
mosquitto_pub -t "protogen/fins/launcher/start/exec" -m 'ring_ding.sh'
sleep 5

echo "Pressing space to start (attempt 1)..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keydown", "display": "left"}'
sleep 0.5
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keyup", "display": "left"}'
sleep 2

echo "Pressing space (attempt 2)..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keydown", "display": "left"}'
sleep 0.5
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keyup", "display": "left"}'
sleep 2

echo "Pressing space (attempt 3)..."
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keydown", "display": "left"}'
sleep 0.5
mosquitto_pub -t "protogen/fins/launcher/input/exec" -m '{"key": "space", "action": "keyup", "display": "left"}'
sleep 2

echo "✓ Ring Ding test complete (should have registered 3 space presses)"
echo ""

mosquitto_pub -t "protogen/fins/launcher/kill/exec" -m ''

echo "=========================================="
echo "All tests complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  1. Doom: Multi-window targeting (left/right independent)"
echo "  2. Super Haxagon: Single-window focused mode"
echo "  3. Ring Ding: Single-window focused mode"
echo ""
echo "Check the game behavior to verify inputs worked correctly."
