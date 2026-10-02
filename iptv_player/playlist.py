"""Parser for the .m3u files in streams/.

Each file is named <country code>[_<source>].m3u and contains entries like:

    #EXTINF:-1 tvg-id="AELatinAmerica.us@Panregional",A&E Latin America (1080p)
    #EXTVLCOPT:http-user-agent=Mozilla/5.0
    http://example.com/live/index.m3u8
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
QUALITY_RE = re.compile(r"\s*\((\d{3,4}[ip]|4K|8K|SD|HD)\)\s*$", re.IGNORECASE)
TAG_RE = re.compile(r"\s*\[(Not 24/7|Geo-blocked)\]\s*$", re.IGNORECASE)
FILENAME_RE = re.compile(r"^(?P<country>[a-z]{2})(?:_(?P<source>[a-z0-9_-]+))?$", re.IGNORECASE)


@dataclass(slots=True)
class Stream:
    """One playable URL."""

    id: str
    name: str                 # name without the quality suffix
    raw_name: str             # name exactly as written in the playlist
    quality: str              # "1080p", "720p", ... or ""
    url: str
    tvg_id: str               # "Channel.us@Feed"
    channel_id: str           # "Channel.us"
    feed_id: str              # "Feed"
    country_code: str         # from the filename, e.g. "us"
    source: str               # from the filename suffix, e.g. "pluto"
    playlist_file: str
    not_24_7: bool = False
    geo_blocked: bool = False
    user_agent: str = ""
    referrer: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "quality": self.quality,
            "url": self.url,
            "source": self.source,
            "country": self.country_code,
            "file": self.playlist_file,
            "needs_headers": bool(self.user_agent or self.referrer),
            "not_24_7": self.not_24_7,
            "geo_blocked": self.geo_blocked,
            "kind": stream_kind(self.url),
        }


def stream_kind(url: str) -> str:
    """Rough format guess, used to pick a player on the page."""
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    if ".m3u8" in path or path.endswith(".m3u"):
        return "hls"
    if path.endswith(".mpd"):
        return "dash"
    if path.endswith((".mp4", ".webm", ".ogg", ".ogv")):
        return "file"
    if path.endswith((".ts", ".flv", ".smil")):
        return "other"
    return "hls"  # most extensionless endpoints here are HLS


def stream_id(url: str) -> str:
    return hashlib.blake2s(url.encode("utf-8"), digest_size=6).hexdigest()


def split_name(raw: str) -> tuple[str, str, bool, bool]:
    """Pull the quality and the status tags off the end of a channel name.

    "Sky News (1080p) [Not 24/7]" -> ("Sky News", "1080p", True, False)
    """
    name = raw.strip()
    not_24_7 = geo_blocked = False

    changed = True
    while changed:
        changed = False
        tag = TAG_RE.search(name)
        if tag:
            label = tag.group(1).lower()
            not_24_7 = not_24_7 or label.startswith("not")
            geo_blocked = geo_blocked or label.startswith("geo")
            name = name[: tag.start()].strip()
            changed = True

    quality = ""
    match = QUALITY_RE.search(name)
    if match:
        quality = match.group(1).lower()
        name = name[: match.start()].strip()

    return name, quality, not_24_7, geo_blocked


def parse_file(path: Path) -> Iterator[Stream]:
    stem = path.stem
    meta = FILENAME_RE.match(stem)
    country = (meta.group("country").lower() if meta else "")
    source = (meta.group("source") or "").lower() if meta else ""

    raw_name = ""
    attrs: dict[str, str] = {}
    opts: dict[str, str] = {}

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                body = line[len("#EXTINF:"):]
                attrs = {k.lower(): v for k, v in ATTR_RE.findall(body)}
                raw_name = body.split(",", 1)[1].strip() if "," in body else ""
                opts = {}
            elif line.startswith("#EXTVLCOPT:"):
                option = line[len("#EXTVLCOPT:"):]
                key, _, value = option.partition("=")
                opts[key.strip().lower()] = value.strip()
            elif line.startswith("#"):
                continue
            elif raw_name or line.startswith(("http://", "https://")):
                tvg_id = attrs.get("tvg-id", "")
                channel_id, _, feed_id = tvg_id.partition("@")
                name, quality, not_24_7, geo_blocked = split_name(raw_name)
                yield Stream(
                    id=stream_id(line),
                    name=name or channel_id or line,
                    raw_name=raw_name,
                    quality=quality,
                    url=line,
                    tvg_id=tvg_id,
                    channel_id=channel_id,
                    feed_id=feed_id,
                    country_code=country,
                    source=source,
                    playlist_file=path.name,
                    not_24_7=not_24_7,
                    geo_blocked=geo_blocked,
                    user_agent=opts.get("http-user-agent", ""),
                    referrer=opts.get("http-referrer", ""),
                    extras={k: v for k, v in attrs.items() if k != "tvg-id"},
                )
                raw_name = ""
                attrs = {}
                opts = {}


def parse_directory(directory: Path) -> list[Stream]:
    streams: list[Stream] = []
    for path in sorted(directory.glob("*.m3u")):
        streams.extend(parse_file(path))
    return streams
