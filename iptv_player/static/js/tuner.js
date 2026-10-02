/* Channel tuner front end: loads the grid from the Flask API and plays the
   selected channel with hls.js (or dash.js for MPEG-DASH), pulling the stream
   through the local relay so CORS and custom headers stop being a problem. */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    search: $("search"),
    grid: $("grid"),
    empty: $("empty"),
    more: $("btn-more"),
    count: $("result-count"),
    country: $("f-country"),
    category: $("f-category"),
    quality: $("f-quality"),
    source: $("f-source"),
    direct: $("opt-direct"),
    adult: $("opt-adult"),
    clear: $("btn-clear"),
    refreshData: $("btn-refresh-data"),
    viewAll: $("view-all"),
    viewFav: $("view-favorites"),
    viewRecent: $("view-recent"),
    player: $("player"),
    video: $("video"),
    status: $("screen-status"),
    npName: $("np-name"),
    npMeta: $("np-meta"),
    npClose: $("np-close"),
    sourceList: $("source-list"),
    btnFav: $("btn-fav"),
    btnVlcLocal: $("btn-vlc-local"),
    btnVlcFile: $("btn-vlc-file"),
    btnCopy: $("btn-copy"),
    btnTest: $("btn-test"),
    toast: $("toast"),
  };

  const state = {
    view: "all",
    page: 1,
    pages: 1,
    loading: false,
    channels: [],
    current: null,
    sourceIndex: 0,
  };

  let engine = null;
  let toastTimer = null;

  /* ------------------------------------------------------------- utilities */

  function toast(message, isError) {
    els.toast.textContent = message;
    els.toast.dataset.state = isError ? "error" : "ok";
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (els.toast.hidden = true), 5000);
  }

  function setStatus(message, kind) {
    if (!message) {
      els.status.hidden = true;
      return;
    }
    els.status.textContent = message;
    els.status.dataset.state = kind || "info";
    els.status.hidden = false;
  }

  function monogram(name) {
    const initials = name
      .replace(/[^A-Za-z0-9 ]/g, " ")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => word[0].toUpperCase())
      .join("");
    if (initials.length >= 2) return initials;
    return Array.from(name.trim()).slice(0, 2).join("");
  }

  const isHd = (q) => ["1080p", "1080i", "1440p", "2160p", "4k", "8k"].includes(q);

  function debounce(fn, wait) {
    let timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, arguments), wait);
    };
  }

  /* ------------------------------------------------------------------ grid */

  function queryString(page) {
    const params = new URLSearchParams();
    if (els.search.value.trim()) params.set("q", els.search.value.trim());
    if (els.country.value) params.set("country", els.country.value);
    if (els.category.value) params.set("category", els.category.value);
    if (els.quality.value) params.set("quality", els.quality.value);
    if (els.source.value) params.set("source", els.source.value);
    if (els.adult.checked) params.set("adult", "1");
    if (state.view === "favorites") params.set("favorites", "1");
    params.set("page", page);
    return params.toString();
  }

  async function load(reset) {
    if (state.loading) return;
    state.loading = true;
    if (reset) {
      state.page = 1;
      state.channels = [];
      els.grid.innerHTML = "";
    }

    try {
      let payload;
      if (state.view === "recent") {
        const response = await fetch("/api/recent");
        payload = await response.json();
        payload.total = payload.items.length;
        payload.pages = 1;
      } else {
        const response = await fetch("/api/channels?" + queryString(state.page));
        payload = await response.json();
      }

      state.pages = payload.pages || 1;
      state.channels = state.channels.concat(payload.items);
      renderCards(payload.items);

      const total = payload.total || 0;
      els.count.textContent = total.toLocaleString() + (total === 1 ? " channel" : " channels");
      els.empty.hidden = total > 0;
      els.more.hidden = state.page >= state.pages;
    } catch (error) {
      toast("Could not load the channel list: " + error.message, true);
    } finally {
      state.loading = false;
    }
  }

  function renderCards(items) {
    const fragment = document.createDocumentFragment();

    items.forEach((channel) => {
      const card = document.createElement("div");
      card.className = "card";
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.dataset.key = channel.key;

      const logo = document.createElement("div");
      logo.className = "logo";
      if (channel.logo) {
        const img = document.createElement("img");
        img.src = channel.logo;
        img.alt = "";
        img.loading = "lazy";
        img.onerror = () => {
          logo.innerHTML = '<span class="monogram">' + monogram(channel.name) + "</span>";
        };
        logo.appendChild(img);
      } else {
        logo.innerHTML = '<span class="monogram">' + monogram(channel.name) + "</span>";
      }

      const body = document.createElement("div");
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = channel.name;

      const sub = document.createElement("div");
      sub.className = "sub";
      sub.textContent =
        (channel.flag ? channel.flag + " " : "") +
        channel.country_name +
        (channel.categories.length ? " · " + channel.categories.slice(0, 2).join(", ") : "");

      const badges = document.createElement("div");
      badges.className = "badges";
      if (channel.quality) {
        const badge = document.createElement("span");
        badge.className = "badge" + (isHd(channel.quality) ? " hd" : "");
        badge.textContent = channel.quality;
        badges.appendChild(badge);
      }
      if (channel.stream_count > 1) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = channel.stream_count + " sources";
        badges.appendChild(badge);
      }
      if (channel.not_24_7) {
        const badge = document.createElement("span");
        badge.className = "badge warn";
        badge.textContent = "not 24/7";
        badges.appendChild(badge);
      }
      if (channel.geo_blocked) {
        const badge = document.createElement("span");
        badge.className = "badge warn";
        badge.textContent = "geo-blocked";
        badges.appendChild(badge);
      }

      const star = document.createElement("button");
      star.className = "star";
      star.title = "Keep in favorites";
      star.textContent = channel.favorite ? "\u2605" : "\u2606";
      star.dataset.on = channel.favorite ? "1" : "0";
      star.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleFavorite(channel, star);
      });

      body.append(title, sub, badges);
      card.append(logo, body, star);
      card.addEventListener("click", () => tune(channel, 0));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          tune(channel, 0);
        }
      });

      fragment.appendChild(card);
    });

    els.grid.appendChild(fragment);
    markCurrent();
  }

  function markCurrent() {
    const key = state.current ? state.current.key : null;
    els.grid.querySelectorAll(".card").forEach((card) => {
      card.setAttribute("aria-current", card.dataset.key === key ? "true" : "false");
    });
  }

  async function toggleFavorite(channel, button) {
    try {
      const response = await fetch("/api/favorite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: channel.key }),
      });
      const payload = await response.json();
      channel.favorite = payload.favorite;
      if (button) {
        button.textContent = payload.favorite ? "\u2605" : "\u2606";
        button.dataset.on = payload.favorite ? "1" : "0";
      }
      if (state.current && state.current.key === channel.key) {
        els.btnFav.textContent = payload.favorite ? "Remove from favorites" : "Add to favorites";
        els.btnFav.dataset.on = payload.favorite ? "1" : "0";
      }
      if (state.view === "favorites" && !payload.favorite) load(true);
    } catch (error) {
      toast("Could not save that favorite: " + error.message, true);
    }
  }

  /* ---------------------------------------------------------------- player */

  function teardown() {
    if (engine && engine.destroy) {
      try {
        engine.destroy();
      } catch (e) {
        /* already gone */
      }
    }
    if (engine && engine.reset) {
      try {
        engine.reset();
      } catch (e) {
        /* already gone */
      }
    }
    engine = null;
    els.video.removeAttribute("src");
    els.video.load();
  }

  function tune(channel, index) {
    state.current = channel;
    state.sourceIndex = index || 0;
    els.player.hidden = false;
    els.npName.textContent = channel.name;
    els.npMeta.textContent =
      (channel.flag ? channel.flag + " " : "") +
      channel.country_name +
      (channel.categories.length ? " · " + channel.categories.join(", ") : "") +
      " · " +
      channel.stream_count +
      (channel.stream_count === 1 ? " source" : " sources");
    els.btnFav.textContent = channel.favorite ? "Remove from favorites" : "Add to favorites";
    els.btnFav.dataset.on = channel.favorite ? "1" : "0";

    if (channel.geo_blocked) {
      toast("Every source for this channel is geo-blocked - it will only play from inside its own country.");
    }
    renderSources(channel);
    markCurrent();
    play(channel.streams[state.sourceIndex]);
    els.player.scrollIntoView({ block: "nearest" });

    fetch("/api/watched", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: channel.key }),
    }).catch(() => {});
  }

  function renderSources(channel) {
    els.sourceList.innerHTML = "";
    channel.streams.forEach((stream, index) => {
      const button = document.createElement("button");
      button.className = "source";
      button.setAttribute("aria-pressed", index === state.sourceIndex ? "true" : "false");
      const parts = [
        stream.quality || "unknown quality",
        stream.source || stream.country.toUpperCase(),
        stream.kind.toUpperCase(),
      ];
      if (stream.not_24_7) parts.push("not 24/7");
      if (stream.geo_blocked) parts.push("geo-blocked");
      const label = parts.join(" · ");
      button.innerHTML = '<span class="tag">' + (index + 1) + "</span><span>" + label + "</span>";
      button.addEventListener("click", () => {
        state.sourceIndex = index;
        renderSources(channel);
        play(stream);
      });
      els.sourceList.appendChild(button);
    });
  }

  function play(stream) {
    teardown();
    if (!stream) {
      setStatus("This channel has no playable source.", "error");
      return;
    }

    const url = els.direct.checked ? stream.url : "/proxy/" + stream.id;
    els.btnVlcFile.href = "/play/" + stream.id + ".m3u";
    setStatus("Tuning in…", "info");

    if (stream.kind === "dash") {
      if (!window.dashjs) {
        setStatus("This is an MPEG-DASH stream and dash.js did not load. Use VLC instead.", "error");
        return;
      }
      engine = window.dashjs.MediaPlayer().create();
      engine.initialize(els.video, url, true);
      engine.on(window.dashjs.MediaPlayer.events.ERROR, (event) => {
        setStatus("DASH error: " + (event.error && event.error.message ? event.error.message : "stream failed") + ". Try another source or VLC.", "error");
      });
      els.video.addEventListener("playing", onPlaying, { once: true });
      return;
    }

    const nativeHls = els.video.canPlayType("application/vnd.apple.mpegurl");

    if (window.Hls && window.Hls.isSupported() && stream.kind !== "file") {
      engine = new window.Hls({
        lowLatencyMode: false,
        backBufferLength: 30,
        manifestLoadingTimeOut: 20000,
        manifestLoadingMaxRetry: 2,
        levelLoadingTimeOut: 20000,
        fragLoadingTimeOut: 30000,
      });
      engine.loadSource(url);
      engine.attachMedia(els.video);
      engine.on(window.Hls.Events.MANIFEST_PARSED, () => {
        els.video.play().catch(() => setStatus("Ready. Press play on the picture.", "info"));
      });
      engine.on(window.Hls.Events.ERROR, (event, data) => {
        if (!data.fatal) return;
        if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) {
          setStatus(describeFailure(data), "error");
          engine.startLoad();
        } else if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
          setStatus("Video glitch - recovering…", "info");
          engine.recoverMediaError();
        } else {
          setStatus(describeFailure(data), "error");
          teardown();
        }
      });
    } else {
      els.video.src = url;
      if (!nativeHls && stream.kind === "hls") {
        setStatus("This browser cannot play HLS on its own. Use the VLC buttons.", "error");
      }
      els.video.play().catch(() => {});
    }

    els.video.addEventListener("playing", onPlaying, { once: true });
  }

  function onPlaying() {
    setStatus("Live", "live");
    setTimeout(() => {
      if (els.status.dataset.state === "live") els.status.hidden = true;
    }, 2500);
  }

  function describeFailure(data) {
    const details = data.details || "";
    if (details.indexOf("manifestLoadError") >= 0 || details.indexOf("manifestLoadTimeOut") >= 0) {
      return "That source did not answer. It may be offline, geo-blocked, or just slow - try another source below, or open it in VLC.";
    }
    if (details.indexOf("levelLoadError") >= 0) {
      return "The channel answered but its quality playlist failed. Try another source below.";
    }
    if (details.indexOf("fragLoadError") >= 0) {
      return "Video chunks are failing to load. Try another source below, or VLC.";
    }
    return "Playback failed (" + (details || "unknown error") + "). Try another source, or VLC.";
  }

  function currentStream() {
    if (!state.current) return null;
    return state.current.streams[state.sourceIndex];
  }

  /* --------------------------------------------------------------- actions */

  els.btnFav.addEventListener("click", () => {
    if (!state.current) return;
    const card = els.grid.querySelector('.card[data-key="' + CSS.escape(state.current.key) + '"]');
    toggleFavorite(state.current, card ? card.querySelector(".star") : null);
  });

  els.btnVlcLocal.addEventListener("click", async () => {
    const stream = currentStream();
    if (!stream) return;
    els.btnVlcLocal.disabled = true;
    try {
      const response = await fetch("/api/vlc/" + stream.id, { method: "POST" });
      const payload = await response.json();
      toast(payload.detail, !payload.ok);
    } catch (error) {
      toast("Could not reach the server: " + error.message, true);
    } finally {
      els.btnVlcLocal.disabled = false;
    }
  });

  els.btnCopy.addEventListener("click", async () => {
    const stream = currentStream();
    if (!stream) return;
    try {
      await navigator.clipboard.writeText(stream.url);
      toast("Stream link copied. Paste it into VLC with Ctrl+N.");
    } catch (error) {
      window.prompt("Copy this stream link:", stream.url);
    }
  });

  els.btnTest.addEventListener("click", async () => {
    const stream = currentStream();
    if (!stream) return;
    els.btnTest.disabled = true;
    els.btnTest.textContent = "Testing…";
    try {
      const response = await fetch("/api/probe/" + stream.id);
      const payload = await response.json();
      toast((payload.ok ? "Source is up: " : "Source is down: ") + payload.detail, !payload.ok);
    } catch (error) {
      toast("Test failed: " + error.message, true);
    } finally {
      els.btnTest.disabled = false;
      els.btnTest.textContent = "Test this source";
    }
  });

  els.npClose.addEventListener("click", () => {
    teardown();
    els.player.hidden = true;
    state.current = null;
    setStatus("");
    markCurrent();
  });

  els.refreshData.addEventListener("click", async () => {
    els.refreshData.disabled = true;
    els.refreshData.textContent = "Updating…";
    toast("Downloading channel logos and categories. This takes a minute.");
    try {
      const response = await fetch("/api/metadata/refresh", { method: "POST" });
      const payload = await response.json();
      const failed = Object.values(payload.results).filter((r) => r.indexOf("failed") === 0);
      toast(failed.length ? "Some files failed to download. Check the terminal." : "Channel data updated. Reloading…", failed.length > 0);
      setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
      toast("Update failed: " + error.message, true);
      els.refreshData.disabled = false;
      els.refreshData.textContent = "Update channel data";
    }
  });

  /* --------------------------------------------------------------- filters */

  function setView(view) {
    state.view = view;
    [["all", els.viewAll], ["favorites", els.viewFav], ["recent", els.viewRecent]].forEach(([name, button]) => {
      button.setAttribute("aria-pressed", name === view ? "true" : "false");
    });
    load(true);
  }

  els.viewAll.addEventListener("click", () => setView("all"));
  els.viewFav.addEventListener("click", () => setView("favorites"));
  els.viewRecent.addEventListener("click", () => setView("recent"));

  els.search.addEventListener("input", debounce(() => {
    if (state.view === "recent") state.view = "all";
    setView(state.view);
  }, 260));

  [els.country, els.category, els.quality, els.source].forEach((select) => {
    select.addEventListener("change", () => {
      if (state.view === "recent") setView("all");
      else load(true);
    });
  });

  els.adult.addEventListener("change", () => {
    fetch("/api/setting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "adult", value: els.adult.checked }),
    }).catch(() => {});
    load(true);
  });

  els.direct.addEventListener("change", () => {
    const stream = currentStream();
    if (stream) play(stream);
    toast(els.direct.checked
      ? "Playing straight from the source. Many channels will fail this way - it is useful for comparing."
      : "Playing through the local relay again.");
  });

  els.clear.addEventListener("click", () => {
    els.search.value = "";
    els.country.value = "";
    els.category.value = "";
    els.quality.value = "";
    els.source.value = "";
    setView("all");
  });

  els.more.addEventListener("click", () => {
    state.page += 1;
    load(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== els.search) {
      event.preventDefault();
      els.search.focus();
      els.search.select();
    }
    if (event.key === "Escape" && !els.player.hidden) els.npClose.click();
  });

  if (els.btnVlcLocal.dataset.missing === "1") {
    els.btnVlcLocal.title = "VLC was not found on this PC. The .m3u download still works.";
  }

  setView("all");
})();
