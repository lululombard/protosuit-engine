#!/usr/bin/env python3
"""
Protosuit Engine - Development Launcher
Starts all three processes (renderer, launcher, web) for local development

⚠️  WARNING: For development only!
Production deployments should use systemd services:
  - protosuit-renderer.service
  - protosuit-launcher.service
  - protosuit-web.service

This is a single point of failure and should not be used in production.
"""

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

    # Start processes
    processes = {
        "renderer": subprocess.Popen(
            [str(python_bin), str(project_root / "renderer" / "renderer.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ),
        "launcher": subprocess.Popen(
            [str(python_bin), str(project_root / "launcher" / "launcher.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ),
        "web": subprocess.Popen(
            [str(python_bin), str(project_root / "web" / "server.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
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
