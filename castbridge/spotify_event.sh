#!/bin/bash
# Spotify event handler for raspotify/librespot
# Called via LIBRESPOT_ONEVENT - publishes raw events to MQTT for CastBridge

MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
TOPIC="protogen/fins/castbridge/spotify/event"

# Escape strings for JSON (handle quotes/backslashes/newlines)
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' '; }

# Build JSON payload from librespot environment variables
# track_changed provides full metadata; other events provide position
JSON=$(printf '{"event":"%s","track_id":"%s","position_ms":%s,"duration_ms":%s,"name":"%s","artists":"%s","album":"%s","covers":"%s"}' \
    "${PLAYER_EVENT:-}" \
    "${TRACK_ID:-}" \
    "${POSITION_MS:-0}" \
    "${DURATION_MS:-0}" \
    "$(json_escape "${NAME:-}")" \
    "$(json_escape "${ARTISTS:-}")" \
    "$(json_escape "${ALBUM:-}")" \
    "$(json_escape "${COVERS:-}")")

mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -t "$TOPIC" -m "$JSON" 2>/dev/null
