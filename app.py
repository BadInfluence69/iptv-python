#!/usr/bin/env python3
"""Run the IPTV browser player.

    python app.py                 start the server and open the page
    python app.py --update-data   fetch channel logos/categories, then start
    python app.py --port 9000     use a different port
    python app.py --lan           listen on the whole network, not just this PC
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from iptv_player import config, metadata
from iptv_player.web import create_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser player for the iptv-org playlists.")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--lan", action="store_true", help="listen on 0.0.0.0 for other devices")
    parser.add_argument("--update-data", action="store_true", help="download channel metadata first")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if not config.STREAMS_DIR.exists():
        print(f"No playlists found at {config.STREAMS_DIR}.")
        print("Run this from the repository root, or set IPTV_STREAMS_DIR.")
        return 1

    if args.update_data or not metadata.have_cache():
        if args.update_data:
            print("Downloading channel metadata (logos, categories, countries)...")
        else:
            print("No cached metadata yet - fetching it once (needs internet).")
            print("If this fails the player still works, with plainer channel cards.")
        metadata.download()

    print("Reading playlists...")
    app = create_app()

    host = "0.0.0.0" if args.lan else args.host
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{args.port}/"
    print(f"\n  Channel grid: {url}")
    print("  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=args.port, debug=args.debug, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
