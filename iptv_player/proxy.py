"""Relays stream data to the browser.

Public IPTV servers almost never send CORS headers, and some need a specific
User-Agent or Referer, so a <video> tag cannot fetch them directly. Every
request goes through here instead: playlists are rewritten so that segment URLs
point back at this server, and segments are streamed through untouched.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urljoin, urlsplit

import requests
import urllib3
from flask import Response, request, stream_with_context

from . import config
from .playlist import Stream

if not config.VERIFY_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URI_ATTR_RE = re.compile(r'URI="([^"]+)"')
SESSION = requests.Session()
SESSION.trust_env = False

BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}
PLAYLIST_TYPES = ("mpegurl", "x-mpegurl", "vnd.apple.mpegurl")
DROP_HEADERS = {
    "content-encoding", "transfer-encoding", "connection", "keep-alive",
    "content-length", "set-cookie", "strict-transport-security",
}


def is_blocked(url: str) -> bool:
    """Light SSRF guard, in case the server is ever exposed beyond localhost."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return True
    host = (parts.hostname or "").lower()
    if not host or host in BLOCKED_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def proxy_path(stream_id: str, url: str) -> str:
    return f"/proxy/{stream_id}?u={quote(url, safe='')}"


def upstream_headers(stream: Stream | None) -> dict:
    headers = {
        "User-Agent": (stream.user_agent if stream and stream.user_agent else config.DEFAULT_USER_AGENT),
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    if stream and stream.referrer:
        headers["Referer"] = stream.referrer
        parts = urlsplit(stream.referrer)
        if parts.scheme and parts.netloc:
            headers["Origin"] = f"{parts.scheme}://{parts.netloc}"
    for name in ("range", "if-none-match", "if-modified-since"):
        value = request.headers.get(name)
        if value:
            headers[name.title()] = value
    return headers


def rewrite_playlist(text: str, base_url: str, stream_id: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append("")
        elif stripped.startswith("#"):
            if "URI=" in stripped:
                stripped = URI_ATTR_RE.sub(
                    lambda m: 'URI="%s"' % proxy_path(stream_id, urljoin(base_url, m.group(1))),
                    stripped,
                )
            out.append(stripped)
        else:
            out.append(proxy_path(stream_id, urljoin(base_url, stripped)))
    return "\n".join(out) + "\n"


def relay(stream: Stream | None, url: str, stream_id: str) -> Response:
    if is_blocked(url):
        return Response("Blocked target address.", status=400, mimetype="text/plain")

    try:
        upstream = SESSION.get(
            url,
            headers=upstream_headers(stream),
            stream=True,
            timeout=(config.CONNECT_TIMEOUT, config.READ_TIMEOUT),
            verify=config.VERIFY_TLS,
            allow_redirects=True,
        )
    except requests.exceptions.SSLError as error:
        return Response(f"TLS handshake failed: {error}", status=502, mimetype="text/plain")
    except requests.exceptions.ConnectTimeout:
        return Response("The channel's server did not answer.", status=504, mimetype="text/plain")
    except requests.RequestException as error:
        return Response(f"Could not reach the channel: {error}", status=502, mimetype="text/plain")

    content_type = upstream.headers.get("Content-Type", "").lower()
    final_url = upstream.url
    looks_like_playlist = (
        any(token in content_type for token in PLAYLIST_TYPES)
        or ".m3u8" in urlsplit(final_url).path.lower()
    )

    if upstream.status_code >= 400:
        upstream.close()
        return Response(
            f"The channel's server answered {upstream.status_code}.",
            status=upstream.status_code if upstream.status_code < 600 else 502,
            mimetype="text/plain",
        )

    if looks_like_playlist:
        body = upstream.raw.read(config.MAX_PLAYLIST_BYTES, decode_content=True)
        upstream.close()
        text = body.decode("utf-8", errors="replace")
        if not text.lstrip().startswith("#EXTM3U"):
            # Some endpoints answer with HTML when a stream is offline.
            return Response(
                "That source did not return a playlist (it may be offline or geo-blocked).",
                status=502,
                mimetype="text/plain",
            )
        rewritten = rewrite_playlist(text, final_url, stream_id)
        response = Response(rewritten, mimetype="application/vnd.apple.mpegurl")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    def pump():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        except requests.RequestException:
            return
        finally:
            upstream.close()

    response = Response(
        stream_with_context(pump()),
        status=upstream.status_code,
        mimetype=content_type.split(";")[0] or "application/octet-stream",
    )
    for name, value in upstream.headers.items():
        if name.lower() in DROP_HEADERS or name.lower() == "content-type":
            continue
        response.headers[name] = value
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def probe(stream: Stream) -> dict:
    """Quick reachability check used by the 'Test source' button."""
    try:
        response = SESSION.get(
            stream.url,
            headers=upstream_headers(stream),
            stream=True,
            timeout=(config.CONNECT_TIMEOUT, 12),
            verify=config.VERIFY_TLS,
            allow_redirects=True,
        )
        head = response.raw.read(2048, decode_content=True) or b""
        status = response.status_code
        content_type = response.headers.get("Content-Type", "")
        response.close()
    except requests.RequestException as error:
        return {"ok": False, "detail": str(error)[:200]}

    text = head.decode("utf-8", errors="replace")
    if status >= 400:
        return {"ok": False, "detail": f"server answered {status}"}
    if text.lstrip().startswith("#EXTM3U"):
        variants = text.count("#EXT-X-STREAM-INF")
        return {
            "ok": True,
            "detail": f"playlist ok, {variants} quality variants" if variants else "playlist ok",
        }
    if "mpegurl" in content_type.lower() or "video" in content_type.lower():
        return {"ok": True, "detail": f"responding ({content_type.split(';')[0]})"}
    return {"ok": False, "detail": f"unexpected response ({content_type or 'unknown type'})"}
