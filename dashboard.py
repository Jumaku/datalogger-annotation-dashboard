#!/usr/bin/env python3
"""Launch the manual supercooling dashboard in a web browser."""

import argparse
import sys
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from freezeplots.manual_dashboard_server import start_dashboard_server


def parse_args():
    parser = argparse.ArgumentParser(
        description="Start the manual supercooling dashboard in a web browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Local HTTP port (default: 8765).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    server, thread, state = start_dashboard_server(port=args.port)
    url = f"http://127.0.0.1:{args.port}/"

    print(f"Dashboard running at {url}")
    print(f"H5 file: {state.hdf5_path}")
    print(f"Annotations CSV: {state.annotations_path}")
    print("Press Ctrl+C to stop the dashboard.")

    try:
        if not webbrowser.open(url, new=2):
            print(f"Could not open a browser automatically. Open {url} manually.")
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
