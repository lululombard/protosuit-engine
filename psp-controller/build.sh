#!/bin/bash

# Build the PSP controller
export PSPDEV=/usr/local/pspdev
export PATH=$PATH:$PSPDEV/bin
make clean
make
