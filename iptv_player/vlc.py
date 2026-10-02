"""Hand a stream to VLC.

Two ways out of the browser:
  * download a one-channel .m3u file (opens in whatever player you associated)
  * launch VLC directly, which works because the server runs on your own PC
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from .playlist import Stream

WINDOWS_PATHS = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]
MAC_PATHS = ["/Applications/VLC.app/Contents/MacOS/VLC"]


def find_vlc() -> str:
    override = os.environ.get("IPTV_VLC_PATH")
    if override and Path(override).exists():
        return override
    found = shutil.which("vlc")
    if found:
        return found
    candidates = WINDOWS_PATHS if sys.platform.startswith("win") else MAC_PATHS
    for path in candidates:
        if Path(path).exists():
            return path
    return ""


def build_m3u(stream: Stream, title: str) -> str:
    lines = ["#EXTM3U"]
    name = f"{title} ({stream.quality})" if stream.quality else title
    lines.append(f'#EXTINF:-1 tvg-id="{stream.tvg_id}",{name}')
    if stream.user_agent:
        lines.append(f"#EXTVLCOPT:http-user-agent={stream.user_agent}")
    if stream.referrer:
        lines.append(f"#EXTVLCOPT:http-referrer={stream.referrer}")
    lines.append(stream.url)
    return "\r\n".join(lines) + "\r\n"


def launch(stream: Stream, title: str) -> dict:
    binary = find_vlc()
    if not binary:
        return {
            "ok": False,
            "detail": "VLC was not found. Install it, or set IPTV_VLC_PATH to vlc.exe.",
        }

    args = [binary, stream.url, f"--meta-title={title}"]
    user_agent = stream.user_agent or config.DEFAULT_USER_AGENT
    args.append(f"--http-user-agent={user_agent}")
    if stream.referrer:
        args.append(f"--http-referrer={stream.referrer}")

    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except OSError as error:
        return {"ok": False, "detail": f"Could not start VLC: {error}"}
    return {"ok": True, "detail": f"Opened {title} in VLC."}
