#!/bin/bash
set -e

# Build and upload ESP32 firmware

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

../env/bin/pio run -t upload

sleep 3

sudo systemctl restart protosuit-espbridge
