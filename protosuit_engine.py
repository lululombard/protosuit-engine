#!/usr/bin/env python3
"""
Protosuit Engine - Development Launcher
Starts all services for local development.

⚠️  WARNING: For development only!
Production deployments should use systemd services (protosuit-*.service).
This is a single point of failure and should not be used in production.
"""

import os
import subprocess
import sys
import signal
import time
from pathlib import Path

# Color codes for output
COLORS = {
    "renderer": "\033[94m",  # Blue
    "launcher": "\033[92m",  # Green
    "web": "\033[93m",  # Yellow
    "bluetoothbridge": "\033[95m",  # Magenta
    "espbridge": "\033[96m",  # Cyan
    "audiobridge": "\033[91m",  # Red
    "controllerbridge": "\033[97m",  # White
    "castbridge": "\033[33m",  # Dark Yellow
    "networkingbridge": "\033[36m",  # Dark Cyan
    "reset": "\033[0m",
}


def main():
    print("=" * 60)
    print("⚠️  PROTOSUIT ENGINE - DEVELOPMENT LAUNCHER")
    print("=" * 60)
    print("Starting all processes...")
    print("Press Ctrl+C to stop all processes\n")

    project_root = Path(__file__).parent
    python_bin = project_root / "env" / "bin" / "python"
    engine_dir = project_root / "engine"

    # Environment with PYTHONPATH pointing to engine/
    env = {**os.environ, 'PYTHONPATH': str(engine_dir)}

    # Start processes
    processes = {
        "renderer": subprocess.Popen(
            [str(python_bin), str(engine_dir / "renderer" / "renderer.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "launcher": subprocess.Popen(
            [str(python_bin), str(engine_dir / "launcher" / "launcher.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "web": subprocess.Popen(
            [str(python_bin), str(engine_dir / "web" / "server.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "bluetoothbridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "bluetoothbridge" / "bluetoothbridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "espbridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "espbridge" / "espbridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "audiobridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "audiobridge" / "audiobridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "controllerbridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "controllerbridge" / "controllerbridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "castbridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "castbridge" / "castbridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
        "networkingbridge": subprocess.Popen(
            [str(python_bin), str(engine_dir / "networkingbridge" / "networkingbridge.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        ),
    }

    def cleanup(sig=None, frame=None):
        """Gracefully stop all processes"""
        print("\n\n" + "=" * 60)
        print("Stopping all processes...")
        print("=" * 60)
        for name, proc in processes.items():
            print(f"Stopping {name}...")
            proc.terminate()

        # Wait for graceful shutdown
        time.sleep(2)

        # Force kill if still running
        for name, proc in processes.items():
            if proc.poll() is None:
                print(f"Force killing {name}...")
                proc.kill()

        print("All processes stopped.")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Monitor and display output
    try:
        import select

        while True:
            # Check if any process has died
            for name, proc in processes.items():
                if proc.poll() is not None:
                    print(
                        f"\n{COLORS[name]}[{name.upper()}] Process exited with code {proc.returncode}{COLORS['reset']}"
                    )
                    cleanup()

            # Read output from processes
            for name, proc in processes.items():
                if proc.stdout and select.select([proc.stdout], [], [], 0)[0]:
                    line = proc.stdout.readline()
                    if line:
                        print(
                            f"{COLORS[name]}[{name.upper()}]{COLORS['reset']} {line.rstrip()}"
                        )

            time.sleep(0.01)

    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
