"""Turns the parsed playlists into the channel grid the page renders.

Several playlist entries often point at the same channel (different mirrors or
different qualities), so entries are grouped: one card per channel, with every
working URL available behind it as a source you can switch between.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import config
from .metadata import Metadata
from .playlist import Stream, parse_directory

QUALITY_ORDER = {
    "8k": 0, "4k": 1, "2160p": 1, "1440p": 2, "1080p": 3, "1080i": 4,
    "720p": 5, "576p": 6, "540p": 7, "480p": 8, "360p": 9, "240p": 10,
    "hd": 5, "sd": 9, "": 11,
}
NON_WORD = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return NON_WORD.sub(" ", text.lower()).strip()


@dataclass(slots=True)
class Channel:
    key: str
    name: str
    channel_id: str
    country_code: str
    country_name: str
    flag: str
    categories: list[str]
    logo: str
    is_nsfw: bool
    streams: list[Stream]
    search_blob: str = ""
    sort_name: str = ""
    sources: set = field(default_factory=set)

    @property
    def best_quality(self) -> str:
        return min(
            (s.quality for s in self.streams),
            key=lambda q: QUALITY_ORDER.get(q, 11),
            default="",
        )

    def to_dict(self, favorite: bool = False) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "channel_id": self.channel_id,
            "country": self.country_code,
            "country_name": self.country_name,
            "flag": self.flag,
            "categories": self.categories,
            "logo": self.logo,
            "quality": self.best_quality,
            "stream_count": len(self.streams),
            "not_24_7": all(s.not_24_7 for s in self.streams),
            "geo_blocked": all(s.geo_blocked for s in self.streams),
            "favorite": favorite,
            "nsfw": self.is_nsfw,
            "streams": [s.to_dict() for s in self.streams],
        }


class Catalog:
    def __init__(self, streams: list[Stream], meta: Metadata) -> None:
        self.meta = meta
        self.streams_by_id: dict[str, Stream] = {s.id: s for s in streams}
        self.channels: list[Channel] = []
        self.by_key: dict[str, Channel] = {}
        self.channel_key_by_stream: dict[str, str] = {}
        self._build(streams)

    @classmethod
    def build(cls) -> "Catalog":
        streams = parse_directory(config.STREAMS_DIR)
        return cls(streams, Metadata.load())

    def _build(self, streams: list[Stream]) -> None:
        grouped: dict[str, list[Stream]] = {}
        for stream in streams:
            if stream.channel_id:
                key = stream.channel_id
            else:
                key = f"{stream.country_code}:{fold(stream.name)}"
            grouped.setdefault(key, []).append(stream)

        meta = self.meta
        for key, items in grouped.items():
            items.sort(key=lambda s: (QUALITY_ORDER.get(s.quality, 11), s.source, s.url))
            first = items[0]
            record = meta.channels.get(first.channel_id, {})
            name = record.get("name") or first.name or key
            country_code = (record.get("country") or first.country_code or "").lower()
            country = meta.country(country_code)
            feed = next((s.feed_id for s in items if s.feed_id), "")

            channel = Channel(
                key=key,
                name=name,
                channel_id=first.channel_id,
                country_code=country_code,
                country_name=country["name"],
                flag=country["flag"],
                categories=meta.category_names(first.channel_id),
                logo=meta.logo_for(first.channel_id, feed),
                is_nsfw=bool(record.get("is_nsfw")),
                streams=items,
            )
            alt = " ".join(record.get("alt_names", []) or [])
            channel.search_blob = fold(
                f"{name} {alt} {first.channel_id} {channel.country_name} "
                f"{' '.join(channel.categories)} {' '.join(s.name for s in items)}"
            )
            channel.sort_name = fold(name) or name.lower()
            channel.sources = {s.source for s in items if s.source}
            self.channels.append(channel)
            self.by_key[key] = channel
            for item in items:
                self.channel_key_by_stream[item.id] = key

        self.channels.sort(key=lambda c: (c.sort_name, c.country_code))

    # ------------------------------------------------------------------ query

    def query(
        self,
        q: str = "",
        country: str = "",
        category: str = "",
        source: str = "",
        quality: str = "",
        favorites: set | None = None,
        only_favorites: bool = False,
        include_nsfw: bool = False,
        page: int = 1,
        per_page: int = config.PAGE_SIZE,
    ) -> dict:
        favorites = favorites or set()
        terms = [t for t in fold(q).split() if t]
        category = category.lower()
        results = []

        for channel in self.channels:
            if not include_nsfw and channel.is_nsfw:
                continue
            if only_favorites and channel.key not in favorites:
                continue
            if country and channel.country_code != country:
                continue
            if category and not any(c.lower() == category for c in channel.categories):
                continue
            if source and source not in channel.sources:
                continue
            if quality and not any(s.quality == quality for s in channel.streams):
                continue
            if terms:
                blob = channel.search_blob
                if not all(term in blob for term in terms):
                    continue
            results.append(channel)

        if terms:
            # exact-ish name matches first, then by name
            prefix = " ".join(terms)
            results.sort(key=lambda c: (not c.search_blob.startswith(prefix), c.sort_name))

        total = len(results)
        page = max(1, page)
        start = (page - 1) * per_page
        items = results[start : start + per_page]
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, -(-total // per_page)),
            "items": [c.to_dict(favorite=c.key in favorites) for c in items],
        }

    # ----------------------------------------------------------------- facets

    def facets(self) -> dict:
        countries: dict[str, dict] = {}
        categories: dict[str, int] = {}
        sources: dict[str, int] = {}
        qualities: dict[str, int] = {}

        for channel in self.channels:
            if channel.is_nsfw:
                continue
            code = channel.country_code
            entry = countries.setdefault(
                code, {"code": code, "name": channel.country_name, "flag": channel.flag, "count": 0}
            )
            entry["count"] += 1
            for name in channel.categories:
                categories[name] = categories.get(name, 0) + 1
            for name in channel.sources:
                sources[name] = sources.get(name, 0) + 1
            quality = channel.best_quality
            if quality:
                qualities[quality] = qualities.get(quality, 0) + 1

        return {
            "countries": sorted(countries.values(), key=lambda c: c["name"]),
            "categories": sorted(
                ({"name": k, "count": v} for k, v in categories.items()),
                key=lambda c: c["name"],
            ),
            "sources": sorted(
                ({"name": k, "count": v} for k, v in sources.items()),
                key=lambda s: -s["count"],
            ),
            "qualities": sorted(
                ({"name": k, "count": v} for k, v in qualities.items()),
                key=lambda q: QUALITY_ORDER.get(q["name"], 11),
            ),
            "channel_count": sum(1 for c in self.channels if not c.is_nsfw),
            "stream_count": len(self.streams_by_id),
            "has_metadata": self.meta.loaded,
        }

    def stream(self, stream_id: str) -> Stream | None:
        return self.streams_by_id.get(stream_id)

    def channel(self, key: str) -> Channel | None:
        return self.by_key.get(key)

    def channel_for_stream(self, stream_id: str) -> Channel | None:
        key = self.channel_key_by_stream.get(stream_id)
        return self.by_key.get(key) if key else None
