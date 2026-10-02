"""Paths and tunables. Everything can be overridden with environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Where the repository's .m3u playlists live.
STREAMS_DIR = Path(os.environ.get("IPTV_STREAMS_DIR", BASE_DIR / "streams"))

# Downloaded channel metadata (names, logos, categories) and your favorites.
DATA_DIR = Path(os.environ.get("IPTV_DATA_DIR", BASE_DIR / "data_cache"))
USER_DATA_FILE = DATA_DIR / "user_data.json"

# Public metadata API that matches these playlists.
API_BASE = os.environ.get("IPTV_API_BASE", "https://iptv-org.github.io/api")
API_FILES = ("channels", "feeds", "logos", "categories", "countries", "languages")

# Server defaults.
HOST = os.environ.get("IPTV_HOST", "127.0.0.1")
PORT = int(os.environ.get("IPTV_PORT", "8700"))

# Many public IPTV servers expect a player-like client and have sloppy TLS
# certificates. Requests through the proxy use these settings.
DEFAULT_USER_AGENT = os.environ.get(
    "IPTV_USER_AGENT", "VLC/3.0.20 LibVLC/3.0.20"
)
VERIFY_TLS = os.environ.get("IPTV_VERIFY_TLS", "0") == "1"
CONNECT_TIMEOUT = float(os.environ.get("IPTV_CONNECT_TIMEOUT", "8"))
READ_TIMEOUT = float(os.environ.get("IPTV_READ_TIMEOUT", "25"))

# Grid page size.
PAGE_SIZE = int(os.environ.get("IPTV_PAGE_SIZE", "48"))

# Largest playlist body the proxy will rewrite (segments stream through, so this
# only caps .m3u8 text).
MAX_PLAYLIST_BYTES = 6 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
