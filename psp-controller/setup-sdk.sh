#!/bin/bash
# PSP SDK Setup Script for Raspberry Pi
# Installs the open-source PSPSDK toolchain

set -e

echo "=========================================="
echo "PSP SDK Setup for Raspberry Pi"
echo "=========================================="
echo ""

# Check if running on ARM
ARCH=$(uname -m)
if [[ ! "$ARCH" =~ ^(arm|aarch64) ]]; then
    echo "Warning: This script is designed for Raspberry Pi (ARM architecture)"
    echo "Current architecture: $ARCH"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Installation directory
PSPDEV="${PSPDEV:-/usr/local/pspdev}"
echo "Installing PSP SDK to: $PSPDEV"
echo ""

# Install dependencies
echo "[1/4] Installing dependencies..."
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    autoconf \
    automake \
    bison \
    flex \
    libgmp3-dev \
    libmpfr-dev \
    libmpc-dev \
    libelf-dev \
    libncurses5-dev \
    libreadline-dev \
    texinfo \
    wget \
    zlib1g-dev \
    libtool-bin \
    libusb-dev \
    pkg-config \
    python3

echo "✓ Dependencies installed"
echo ""

# Create installation directory
echo "[2/4] Setting up installation directory..."
sudo mkdir -p "$PSPDEV"
sudo chown -R $(whoami):$(whoami) "$PSPDEV"
echo "✓ Directory created: $PSPDEV"
echo ""

# Clone psptoolchain
echo "[3/4] Cloning psptoolchain repository..."
TOOLCHAIN_DIR="$HOME/psptoolchain"
if [ -d "$TOOLCHAIN_DIR" ]; then
    echo "Toolchain directory already exists, pulling latest..."
    cd "$TOOLCHAIN_DIR"
    git pull
else
    git clone https://github.com/pspdev/psptoolchain.git "$TOOLCHAIN_DIR"
    cd "$TOOLCHAIN_DIR"
fi
echo "✓ Repository ready"
echo ""

# Build toolchain
echo "[4/4] Building PSP toolchain (this will take a while)..."
echo "Building in: $(pwd)"
export PSPDEV="$PSPDEV"
export PATH="$PATH:$PSPDEV/bin"

# Run the toolchain build script
./toolchain.sh

echo ""
echo "=========================================="
echo "✓ PSP SDK Installation Complete!"
echo "=========================================="
echo ""
echo "Add these lines to your ~/.bashrc or ~/.zshrc:"
echo ""
echo "  export PSPDEV=$PSPDEV"
echo "  export PATH=\$PATH:\$PSPDEV/bin"
echo ""
echo "Then run: source ~/.bashrc  (or ~/.zshrc)"
echo ""
echo "To verify installation, run: psp-gcc --version"
echo ""

