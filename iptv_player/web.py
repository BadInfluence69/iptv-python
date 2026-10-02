"""Flask app: serves the channel grid and everything it talks to."""

from __future__ import annotations

import threading
from urllib.parse import unquote

from flask import Flask, Response, jsonify, render_template, request

from . import config, metadata, proxy, vlc
from .catalog import Catalog
from .store import UserData

_lock = threading.Lock()


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["JSON_SORT_KEYS"] = False

    state = {"catalog": Catalog.build()}
    user_data = UserData()

    def catalog() -> Catalog:
        return state["catalog"]

    # ------------------------------------------------------------------ pages

    @app.route("/")
    def index():
        facets = catalog().facets()
        return render_template(
            "index.html",
            facets=facets,
            vlc_available=bool(vlc.find_vlc()),
            settings=user_data.settings,
        )

    # -------------------------------------------------------------------- api

    @app.get("/api/facets")
    def api_facets():
        return jsonify(catalog().facets())

    @app.get("/api/channels")
    def api_channels():
        args = request.args
        result = catalog().query(
            q=args.get("q", "").strip(),
            country=args.get("country", "").strip().lower(),
            category=args.get("category", "").strip(),
            source=args.get("source", "").strip().lower(),
            quality=args.get("quality", "").strip().lower(),
            favorites=user_data.favorite_set,
            only_favorites=args.get("favorites") == "1",
            include_nsfw=args.get("adult") == "1",
            page=int(args.get("page", 1) or 1),
            per_page=min(200, int(args.get("per_page", config.PAGE_SIZE) or config.PAGE_SIZE)),
        )
        return jsonify(result)

    @app.get("/api/channel")
    def api_channel():
        channel = catalog().channel(request.args.get("key", ""))
        if not channel:
            return jsonify({"error": "No such channel."}), 404
        return jsonify(channel.to_dict(favorite=channel.key in user_data.favorite_set))

    @app.post("/api/favorite")
    def api_favorite():
        key = (request.get_json(silent=True) or {}).get("key", "")
        if not catalog().channel(key):
            return jsonify({"error": "No such channel."}), 404
        return jsonify({"key": key, "favorite": user_data.toggle_favorite(key)})

    @app.post("/api/watched")
    def api_watched():
        payload = request.get_json(silent=True) or {}
        key = payload.get("key", "")
        channel = catalog().channel(key)
        if channel:
            user_data.remember(key, channel.name)
        return jsonify({"ok": True})

    @app.get("/api/recent")
    def api_recent():
        items = []
        for entry in user_data.recent[:24]:
            channel = catalog().channel(entry.get("key", ""))
            if channel:
                items.append(channel.to_dict(favorite=channel.key in user_data.favorite_set))
        return jsonify({"items": items})

    @app.post("/api/setting")
    def api_setting():
        payload = request.get_json(silent=True) or {}
        name, value = payload.get("name"), payload.get("value")
        if not name:
            return jsonify({"error": "Setting name is required."}), 400
        user_data.set_setting(str(name), value)
        return jsonify({"ok": True, "settings": user_data.settings})

    @app.get("/api/probe/<stream_id>")
    def api_probe(stream_id: str):
        stream = catalog().stream(stream_id)
        if not stream:
            return jsonify({"error": "No such source."}), 404
        return jsonify(proxy.probe(stream))

    @app.post("/api/reload")
    def api_reload():
        with _lock:
            state["catalog"] = Catalog.build()
        return jsonify(catalog().facets())

    @app.post("/api/metadata/refresh")
    def api_metadata_refresh():
        results = metadata.download()
        with _lock:
            state["catalog"] = Catalog.build()
        return jsonify({"results": results, "facets": catalog().facets()})

    # ------------------------------------------------------------- playback

    @app.get("/proxy/<stream_id>")
    def route_proxy(stream_id: str):
        stream = catalog().stream(stream_id)
        target = request.args.get("u")
        if target:
            target = unquote(target)
        elif stream:
            target = stream.url
        else:
            return Response("Unknown source.", status=404, mimetype="text/plain")
        return proxy.relay(stream, target, stream_id)

    @app.get("/play/<stream_id>.m3u")
    def route_m3u(stream_id: str):
        stream = catalog().stream(stream_id)
        if not stream:
            return Response("Unknown source.", status=404, mimetype="text/plain")
        channel = catalog().channel_for_stream(stream_id)
        title = channel.name if channel else stream.name
        body = vlc.build_m3u(stream, title)
        safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "channel"
        return Response(
            body,
            mimetype="audio/x-mpegurl",
            headers={"Content-Disposition": f'attachment; filename="{safe}.m3u"'},
        )

    @app.post("/api/vlc/<stream_id>")
    def route_vlc(stream_id: str):
        stream = catalog().stream(stream_id)
        if not stream:
            return jsonify({"ok": False, "detail": "Unknown source."}), 404
        channel = catalog().channel_for_stream(stream_id)
        title = channel.name if channel else stream.name
        return jsonify(vlc.launch(stream, title))

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "vlc": bool(vlc.find_vlc()),
                "metadata": catalog().meta.loaded,
                "streams_dir": str(config.STREAMS_DIR),
            }
        )

    return app
