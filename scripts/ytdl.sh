#!/usr/bin/env bash
set -euo pipefail

# Get the absolute path of the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../assets/video"

# Ask for YouTube link if not provided
if [ $# -lt 1 ]; then
  read -rp "Enter YouTube link: " YT_URL
else
  YT_URL="$1"
fi

# Ask for filename if not provided
if [ $# -lt 2 ]; then
  read -rp "Enter output file name (without extension): " FILE_NAME
else
  FILE_NAME="$2"
fi

# Ensure target directory exists
mkdir -p "$OUTPUT_DIR"

OUTPUT_PATH="${OUTPUT_DIR}/${FILE_NAME}.mp4"

# Temp file for the full downloaded video
TMP_DIR="${SCRIPT_DIR}/.tmp_yt"
mkdir -p "$TMP_DIR"
TMP_FILE="${TMP_DIR}/${FILE_NAME}.source.mp4"

echo "Downloading video with yt-dlp..."
echo "→ Source: $YT_URL"
echo "→ Temp:   $TMP_FILE"

# Download best video+audio as mp4 (merged by yt-dlp)
yt-dlp \
  -f "bv*+ba/best" \
  --merge-output-format mp4 \
  -o "$TMP_FILE" \
  "$YT_URL"

echo "Scaling to 720 height, cropping sides to 720x720..."
echo "→ Output: $OUTPUT_PATH"

ffmpeg -y -i "$TMP_FILE" \
  -vf "scale=-1:720,crop=720:720:(in_w-720)/2:0" \
  -c:v libx264 -preset fast -crf 18 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUTPUT_PATH"

echo "Cleaning up temp file..."
rm -f "$TMP_FILE"

echo "✅ Done! Saved to $OUTPUT_PATH"