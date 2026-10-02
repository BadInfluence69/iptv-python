"""Optional channel metadata: logos, categories, country names, languages.

The playlists only carry a name and a tvg-id, so the extra detail comes from the
public iptv-org API and is cached in data_cache/. The app runs fine without it:
every lookup falls back to what the playlist itself provides.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from . import config

LOGO_FORMAT_RANK = {"SVG": 0, "PNG": 1, "WEBP": 2, "JPEG": 3, "GIF": 4, "APNG": 5}


def _cache_path(name: str) -> Path:
    return config.DATA_DIR / f"{name}.json"


def have_cache() -> bool:
    return _cache_path("channels").exists()


def download(files=config.API_FILES, log=print) -> dict:
    """Fetch metadata files into data_cache/. Returns {name: ok_or_error}."""
    results = {}
    session = requests.Session()
    for name in files:
        url = f"{config.API_BASE}/{name}.json"
        try:
            log(f"  downloading {name}.json ...")
            response = session.get(url, timeout=(config.CONNECT_TIMEOUT, 90))
            response.raise_for_status()
            payload = response.json()
            target = _cache_path(name)
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(payload), encoding="utf-8")
            temp.replace(target)
            results[name] = f"ok ({len(payload)} records)"
        except Exception as error:  # network, JSON, disk - all non-fatal
            results[name] = f"failed: {error}"
            log(f"  {name}.json failed: {error}")
    return results


def _read(name: str):
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def flag_for(code: str) -> str:
    """Flag emoji from a two-letter country code, no data file needed."""
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return "\N{TELEVISION}"
    return chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)


class Metadata:
    """Lookups used while building the catalog. Empty when nothing is cached."""

    def __init__(self) -> None:
        self.channels: dict[str, dict] = {}
        self.logos: dict[str, str] = {}          # "Channel.us" or "Channel.us@Feed" -> url
        self.categories: dict[str, str] = {}     # "news" -> "News"
        self.countries: dict[str, dict] = {}     # "us" -> {"name": ..., "flag": ...}
        self.languages: dict[str, str] = {}
        self.feeds: dict[str, dict] = {}
        self.loaded = False

    @classmethod
    def load(cls) -> "Metadata":
        meta = cls()

        for record in _read("channels") or []:
            if isinstance(record, dict) and record.get("id"):
                meta.channels[record["id"]] = record
                if record.get("logo"):  # older API shape
                    meta.logos.setdefault(record["id"], record["logo"])

        best: dict[str, tuple] = {}
        for record in _read("logos") or []:
            if not isinstance(record, dict) or not record.get("url"):
                continue
            channel = record.get("channel")
            if not channel:
                continue
            feed = record.get("feed")
            key = f"{channel}@{feed}" if feed else channel
            rank = (
                LOGO_FORMAT_RANK.get(str(record.get("format", "")).upper(), 9),
                abs((record.get("width") or 320) - 320),
            )
            if key not in best or rank < best[key][0]:
                best[key] = (rank, record["url"])
            if channel not in best or rank < best[channel][0]:
                best[channel] = (rank, record["url"])
        for key, (_, url) in best.items():
            meta.logos[key] = url

        for record in _read("categories") or []:
            if isinstance(record, dict) and record.get("id"):
                meta.categories[record["id"]] = record.get("name", record["id"])

        for record in _read("countries") or []:
            if isinstance(record, dict) and record.get("code"):
                meta.countries[record["code"].lower()] = {
                    "name": record.get("name", record["code"]),
                    "flag": record.get("flag") or flag_for(record["code"]),
                }

        for record in _read("languages") or []:
            if isinstance(record, dict) and record.get("code"):
                meta.languages[record["code"]] = record.get("name", record["code"])

        for record in _read("feeds") or []:
            if isinstance(record, dict) and record.get("channel"):
                meta.feeds[f"{record['channel']}@{record.get('id')}"] = record

        meta.loaded = bool(meta.channels or meta.countries)
        return meta

    def country(self, code: str) -> dict:
        code = (code or "").lower()
        if code in self.countries:
            return self.countries[code]
        return {"name": code.upper() or "Unknown", "flag": flag_for(code)}

    def logo_for(self, channel_id: str, feed_id: str = "") -> str:
        if feed_id:
            url = self.logos.get(f"{channel_id}@{feed_id}")
            if url:
                return url
        return self.logos.get(channel_id, "")

    def category_names(self, channel_id: str) -> list[str]:
        record = self.channels.get(channel_id) or {}
        return [self.categories.get(c, c.title()) for c in record.get("categories", [])]
