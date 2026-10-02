# Channel tuner — the Python side of this repository

The original project is a Node/TypeScript toolchain that *maintains* the `.m3u`
playlists in `streams/`. Nothing about that changed. What is new is a Python app
that *uses* those playlists: it reads all 325 of them, builds a searchable grid
of about 11,800 channels, and plays them in the browser or hands them to VLC.

![what it does](https://img.shields.io/badge/-no%20build%20step-black) Pure
Python plus two JavaScript files that ship with it. No Node, no npm.

## Getting started

```
pip install -r requirements.txt
python app.py
```

The page opens at <http://127.0.0.1:8700/>. On Windows you can double-click
`run_windows.bat` instead, which sets up a virtual environment the first time
and starts the server after that.

The first run downloads channel logos, categories and country names from the
public iptv-org API into `data_cache/` (about 15 MB). If that fails you still
get a working grid, just with plainer cards — press **Update channel data** in
the top bar whenever you want to retry.

## Using the page

- **Search** matches channel names, countries and categories. Press `/` from
  anywhere to jump into the box.
- **Filters** down the left narrow by country, category, picture quality and
  provider (Pluto, Samsung, Rakuten and the rest).
- **Click a card to tune it.** The player appears above the grid.
- Channels often have several sources. They are listed under the player,
  sorted best-picture-first, and you can switch between them with one click
  when one goes down.
- **Test this source** asks the server to fetch the stream and reports what
  came back, which tells you whether a channel is dead or just slow.
- The star on each card saves a favorite. Favorites and recently watched live in
  `data_cache/user_data.json`, so they survive browser clearing and follow you
  between browsers.

Badges on a card come from the playlist itself: `not 24/7` means the channel
only broadcasts part of the day, and `geo-blocked` means it will refuse to play
outside its own country.

## Watching in VLC

Three ways out of the browser, all on the player panel:

| Button | What happens |
| --- | --- |
| **Play in VLC** | The server launches VLC on this PC with the right User-Agent and Referer already set |
| **Download .m3u** | Saves a one-channel playlist file; double-click it to open in whatever player you associated |
| **Copy stream link** | Puts the raw URL on the clipboard for `Ctrl+N` in VLC |

If VLC is installed somewhere unusual, set `IPTV_VLC_PATH` to the full path of
`vlc.exe` before starting the server.

## Why playback goes through the local server

Public IPTV servers do not send CORS headers, and a fair number require a
specific User-Agent or Referer before they hand over video. A `<video>` tag in a
browser cannot satisfy either condition, which is why these playlists normally
only work in a desktop player.

So the Flask app relays the stream: it fetches the `.m3u8` playlist itself,
rewrites every segment URL to point back at `/proxy/...`, and streams the video
chunks through. The browser only ever talks to `127.0.0.1`, which keeps it
happy, and the server adds whatever headers the playlist asked for.

**Play without the local relay** in the sidebar turns that off and points the
player straight at the source. Most channels fail that way; it is there for
comparison and for the few sources that are already CORS-friendly.

## When a channel will not play

These playlists are community-maintained and point at servers that come and go,
so some fraction is always broken. In rough order of likelihood:

1. **Try another source** under the player — different mirrors of the same
   channel fail independently.
2. **Test this source.** "Source is down" means the server did not answer;
   "playlist ok" means the problem is on the playback side.
3. **Try VLC.** VLC tolerates odd streams a browser will not touch, including
   the raw `.ts` and `.flv` endpoints in here.
4. **Check the badges.** A geo-blocked channel will not play from outside its
   country without a VPN.

MPEG-DASH channels (about 230 of them) play through dash.js and are not relayed,
since DASH manifests need their original base URLs. If one fails, use VLC.

## Layout

```
app.py                      start here
requirements.txt
run_windows.bat
iptv_player/
    config.py               paths, timeouts, defaults (all overridable by env)
    playlist.py             .m3u parser for the files in streams/
    metadata.py             logo/category/country lookups + their download
    catalog.py              groups streams into channels; search and filters
    store.py                favorites and recently watched
    proxy.py                the relay that makes browser playback work
    vlc.py                  finds VLC, launches it, writes single-channel .m3u
    web.py                  Flask routes
    templates/index.html
    static/css/tuner.css
    static/js/tuner.js
    static/vendor/          hls.js and dash.js, bundled so this works offline
data_cache/                 downloaded metadata, favorites (created on first run)
```

## Settings

Everything below is an environment variable, and the defaults are in
`iptv_player/config.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `IPTV_PORT` | `8700` | Port to serve on |
| `IPTV_STREAMS_DIR` | `./streams` | Where the `.m3u` files are |
| `IPTV_DATA_DIR` | `./data_cache` | Metadata cache and your favorites |
| `IPTV_VLC_PATH` | auto-detected | Full path to `vlc.exe` |
| `IPTV_USER_AGENT` | a VLC string | Sent to servers that check |
| `IPTV_VERIFY_TLS` | `0` | Set to `1` to enforce certificate checks; a lot of these servers have broken certificates |
| `IPTV_PAGE_SIZE` | `48` | Cards per page |

Command line:

```
python app.py --update-data     refresh logos and categories first
python app.py --port 9000
python app.py --lan             serve to other devices on your network
python app.py --no-browser
```

`--lan` makes the relay reachable by anything on your network, so only use it at
home. The relay refuses to fetch private and loopback addresses either way.

## Keeping the playlists current

The `.m3u` files are the repository's own data. Pull the repo (or re-download
it) to get updated channels, then either restart the server or
`POST /api/reload` to re-read them without restarting.

## The API, if you want to script against it

| Route | Purpose |
| --- | --- |
| `GET /api/channels?q=&country=&category=&quality=&source=&page=` | Paged channel search |
| `GET /api/channel?key=` | One channel with all its sources |
| `GET /api/facets` | Country, category, quality and provider lists with counts |
| `GET /api/probe/<stream_id>` | Is this source alive? |
| `GET /proxy/<stream_id>` | Relayed playlist and segments |
| `GET /play/<stream_id>.m3u` | Single-channel playlist file |
| `POST /api/vlc/<stream_id>` | Launch VLC on the server's machine |
| `POST /api/favorite` `{"key": ...}` | Toggle a favorite |
| `POST /api/reload` | Re-read `streams/` |

Resizing the whole interface is one number: `font-size` on the `:root` rule at
the top of `static/css/tuner.css`.
