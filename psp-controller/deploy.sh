#!/bin/bash

# Deploy EBOOT.PBP to PSP(s) via FTP
# Usage: ./deploy.sh <PSP_IP_ADDRESS> [PSP_IP_ADDRESS2 ...]
# Make sure FTP server is running on your PSP (e.g., via ftpd homebrew)

if [ -z "$1" ]; then
    echo "Usage: $0 <PSP_IP_ADDRESS> [PSP_IP_ADDRESS2 ...]"
    echo "Example: $0 192.168.1.100"
    echo "Example: $0 192.168.1.100 192.168.1.101 192.168.1.102"
    exit 1
fi

PSP_IPS=("$@")
PSP_PORT="${PSP_PORT:-21}"  # Default FTP port, can be overridden with env var
PSP_USER="${PSP_USER:-anonymous}"  # Can be overridden with env var
PSP_PASS="${PSP_PASS:-}"  # Can be overridden with env var

# Path on PSP
REMOTE_DIR="/PSP/GAME/ProtosuitRemote"
LOCAL_FILE="EBOOT.PBP"

# Check if EBOOT.PBP exists
if [ ! -f "$LOCAL_FILE" ]; then
    echo "Error: $LOCAL_FILE not found. Run ./build.sh first."
    exit 1
fi

echo "================================================"
echo "Deploying Protosuit Remote Control to PSP(s)"
echo "================================================"
echo "Target PSPs: ${#PSP_IPS[@]}"
echo "Target dir:  $REMOTE_DIR"
echo "Local file:  $LOCAL_FILE ($(du -h $LOCAL_FILE | cut -f1))"
echo "================================================"
echo ""

# Arrays to track results
declare -a SUCCESS_IPS
declare -a FAILED_IPS

# Function to deploy to a single PSP
deploy_to_psp() {
    local PSP_IP=$1
    local PSP_INDEX=$2

    echo "[$PSP_INDEX/${#PSP_IPS[@]}] Deploying to $PSP_IP..."

    # Try lftp first (better), fall back to ftp
    if command -v lftp &> /dev/null; then
        # PSP FTP is very basic, no auth required
        lftp -c "
            set ftp:passive-mode off
            set net:max-retries 1
            set net:timeout 15
            open ftp://$PSP_IP:$PSP_PORT
            mkdir -p $REMOTE_DIR
            cd $REMOTE_DIR
            put $LOCAL_FILE
            bye
        " 2>&1 | grep -v "^$"  # Filter empty lines

        if [ ${PIPESTATUS[0]} -eq 0 ]; then
            echo "  ✓ Success: $PSP_IP"
            SUCCESS_IPS+=("$PSP_IP")
            return 0
        else
            echo "  ✗ Failed: $PSP_IP"
            FAILED_IPS+=("$PSP_IP")
            return 1
        fi
    else
        echo "lftp not installed, install it with: sudo apt install lftp"
        exit 1
    fi
}

# Deploy to each PSP
PSP_INDEX=1
for PSP_IP in "${PSP_IPS[@]}"; do
    deploy_to_psp "$PSP_IP" "$PSP_INDEX"
    echo ""
    PSP_INDEX=$((PSP_INDEX + 1))
done

echo "================================================"
echo "Deployment Summary"
echo "================================================"
echo "Total PSPs: ${#PSP_IPS[@]}"
echo "Successful: ${#SUCCESS_IPS[@]}"
echo "Failed:     ${#FAILED_IPS[@]}"

if [ ${#SUCCESS_IPS[@]} -gt 0 ]; then
    echo ""
    echo "✓ Successfully deployed to:"
    for ip in "${SUCCESS_IPS[@]}"; do
        echo "  - $ip"
    done
fi

if [ ${#FAILED_IPS[@]} -gt 0 ]; then
    echo ""
    echo "✗ Failed to deploy to:"
    for ip in "${FAILED_IPS[@]}"; do
        echo "  - $ip"
    done
    echo ""
    echo "Make sure FTP server is running on failed PSPs"
    exit 1
fi

echo ""
echo "Navigate to Game → Memory Stick on your PSP(s) to run"
echo "================================================"
