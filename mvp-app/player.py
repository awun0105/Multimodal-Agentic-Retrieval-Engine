"""Shared video player adapter for the Query Text and TRAKE tabs.

Source resolution order per keyframe selection:
    1. local proxy MP4 from VIDEO_ROOT   -> Calculated frames (rVFC mediaTime)
    2. valid YouTube watch_url           -> Estimated frames (IFrame API)
    3. neither                           -> keyframe-only notice, still pinnable

Exactly one live number is displayed ("Current frame"); the canonical
keyframe_idx stays implicit as the pinning fallback. The browser keeps the
latest presented frame in window.__aiouPlayers[<id>].latest and the pin
callbacks receive it explicitly — the server never recomputes frames from time.
"""

from __future__ import annotations

import html
import json

from youtube_url import extract_youtube_id


def resolve_player_source(
    *,
    local_path: str | None,
    watch_url: str | None,
) -> tuple[str, str | None]:
    """Return (kind, source_ref) where kind is 'local' | 'youtube' | 'none'."""
    if local_path:
        return "local", str(local_path)
    youtube_id = extract_youtube_id(watch_url)
    if youtube_id:
        return "youtube", youtube_id
    return "none", None


_ACCURACY_LABEL_JS = """
function __aiouAccuracyLabel(kind){
  return kind === 'calculated' ? 'Calculated' :
         kind === 'estimated' ? 'Estimated' : 'Keyframe only';
}
"""

_PLAYER_HEAD_JS = """
(function(){
  function normalize(t){ return Number(Number(t).toPrecision(6)); }
  window.__aiouNormalizeTime = normalize;

  window.__aiouPlayers = window.__aiouPlayers || {};

  window.__aiouFrameSnapshot = function(pid){
    var s = window.__aiouPlayers[pid];
    if (!s || !s.latest || s.latest.frame === null || s.latest.frame === undefined){
      return {frame: null, accuracy: 'none', seeking: false};
    }
    return {frame: s.latest.frame, accuracy: s.latest.accuracy, seeking: !!s.seeking};
  };

  window.__aiouStep = function(pid, delta){
    var s = window.__aiouPlayers[pid];
    if (!s || !s.fps) return;
    var stepTime = delta / s.fps;
    if (s.kind === 'local'){
      var v = s.video;
      if (!v || !isFinite(v.duration)) return;
      v.pause();
      var dur = Math.max(v.duration - stepTime, 0);
      v.currentTime = Math.min(Math.max(v.currentTime + stepTime, 0), dur);
      // seeking flag is raised by the 'seeking' listener; the presented-frame
      // callback clears it, so the shown number follows the real frame.
    } else if (s.kind === 'youtube' && s.yt && s.yt.getCurrentTime){
      var p = s.yt;
      p.pauseVideo();
      var cur = p.getCurrentTime() || 0;
      var ydur = p.getDuration() || 0;
      var limit = ydur > 0 ? Math.max(ydur - stepTime, 0) : Number.MAX_VALUE;
      p.seekTo(Math.min(Math.max(cur + stepTime, 0), limit), true);
    }
  };

  // ---- Lazy YouTube IFrame API loader -------------------------------------
  var ytState = {apiReady: false, loading: false, waiting: []};
  function flushWaiting(){ var q = ytState.waiting.splice(0); q.forEach(function(fn){ fn(); }); }
  window.onYouTubeIframeAPIReady = function(){ ytState.apiReady = true; flushWaiting(); };
  window.__aiouEnsureYT = function(cb){
    if (ytState.apiReady && window.YT && window.YT.Player){ cb(); return; }
    ytState.waiting.push(cb);
    if (ytState.loading) return;
    ytState.loading = true;
    var tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  };
})();
"""

_BOOT_JS = """
window.__aiouPlayerBoot = window.__aiouPlayerBoot || function(svgEl){
  if (svgEl.dataset.booted){ return; }
  svgEl.dataset.booted = '1';
  window.__aiouBootCount = (window.__aiouBootCount || 0) + 1;
  var cfg;
  try { cfg = JSON.parse(svgEl.dataset.player); } catch (err) { return; }
  var pid = cfg.id;
  var registry = window.__aiouPlayers;
  var prev = registry[pid];
  if (prev && prev.destroy) { try { prev.destroy(); } catch (e) {} }

  var frameEl = document.getElementById(pid + '-frame');
  var accEl = document.getElementById(pid + '-accuracy');
  var pinBtn = cfg.pinButtonId ? document.getElementById(cfg.pinButtonId) : null;
  var linkEl = document.getElementById(pid + '-link');

  function label(text, cls){
    if (accEl){ accEl.textContent = text; accEl.className = 'aiou-acc ' + cls; }
  }
  function setFrame(frame, accuracy){
    if (frameEl){ frameEl.textContent = (frame === null || frame === undefined) ? '\\u2014' : String(frame); }
    if (accuracy === 'calculated'){ label('Calculated', 'ok'); }
    else if (accuracy === 'estimated'){ label('Estimated', 'warn'); }
    else { label('Keyframe only', 'muted'); }
    if (pinBtn){ pinBtn.disabled = false; }
  }
  function pinOff(){ if (pinBtn){ pinBtn.disabled = true; } }

  var st = {
    id: pid, kind: cfg.kind, fps: cfg.fps, start: cfg.start,
    latest: {frame: null, accuracy: 'none'},
    seeking: false, raf: null, timer: null, yt: null,
    video: null, listeners: [],
    destroy: function(){
      if (st.raf !== null && st.video && st.video.cancelVideoFrameCallback){
        try { st.video.cancelVideoFrameCallback(st.raf); } catch (e) {}
      }
      st.listeners.forEach(function(entry){
        entry.el.removeEventListener(entry.type, entry.fn);
      });
      st.listeners = [];
      if (st.timer){ clearInterval(st.timer); st.timer = null; }
      if (st.yt && st.yt.destroy){ try { st.yt.destroy(); } catch (e) {} }
      delete registry[pid];
    }
  };
  registry[pid] = st;

  function listen(el, type, fn){
    el.addEventListener(type, fn);
    st.listeners.push({el: el, type: type, fn: fn});
  }

  if (cfg.kind === 'local'){
    var v = document.getElementById(pid);
    if (!v){ setFrame(null, 'none'); return; }
    st.video = v;
    var hasRVFC = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;
    var present = function(_now, meta){
      var t = window.__aiouNormalizeTime(meta.mediaTime);
      st.latest = {frame: Math.floor(t * st.fps), accuracy: 'calculated'};
      setFrame(st.latest.frame, 'calculated');
      if (st.seeking){ st.seeking = false; if (pinBtn){ pinBtn.disabled = false; } }
      if (hasRVFC){ st.raf = v.requestVideoFrameCallback(present); }
    };
    var onSeekStart = function(){
      st.seeking = true; pinOff();
    };
    var onSeekEndFallback = function(){
      if (hasRVFC) return; // the presented callback owns re-enabling
      var t = window.__aiouNormalizeTime(v.currentTime);
      st.latest = {frame: Math.floor(t * st.fps), accuracy: 'estimated'};
      setFrame(st.latest.frame, 'estimated');
      st.seeking = false;
    };
    listen(v, 'seeking', onSeekStart);
    listen(v, 'seeked', onSeekEndFallback);
    listen(v, 'error', function(){
      st.kind = 'none';
      setFrame(null, 'none');
      if (linkEl){ linkEl.style.display = 'inline'; }
    });
    listen(v, 'loadedmetadata', function(){
      if (cfg.start > 0){ try { v.currentTime = cfg.start; } catch (e) {} }
    });
    if (!hasRVFC){
      listen(v, 'timeupdate', function(){
        var t = window.__aiouNormalizeTime(v.currentTime);
        st.latest = {frame: Math.floor(t * st.fps), accuracy: 'estimated'};
        setFrame(st.latest.frame, 'estimated');
      });
    }
    v.pause();
    if (cfg.start > 0){ try { v.currentTime = cfg.start; } catch (e) {} }
    if (hasRVFC){ st.raf = v.requestVideoFrameCallback(present); }
    else { setFrame(Math.floor(window.__aiouNormalizeTime(cfg.start) * st.fps), 'estimated'); }
    return;
  }

  if (cfg.kind === 'youtube'){
    setFrame(null, 'estimated');
    window.__aiouEnsureYT(function(){
      var holder = document.getElementById(pid + '-yt');
      if (!holder) return;
      // Construct WITHOUT videoId: passing one here uses loadVideo semantics,
      // which starts playback. cueVideoById in onReady stays PAUSED/cued.
      var player = new YT.Player(holder, {
        playerVars: {rel: 0, modestbranding: 1, playsinline: 1, autoplay: 0},
        events: {
          onReady: function(ev){
            // Fractional seconds matter: flooring start loses up to a full
            // second (~10-30 frames) and lands before the keyframe.
            ev.target.cueVideoById({
              videoId: cfg.videoId,
              startSeconds: Math.max(cfg.start, 0)
            });
          },
          onError: function(){
            if (st.timer){ clearInterval(st.timer); st.timer = null; }
            if (holder && holder.parentNode){
              holder.parentNode.innerHTML =
                '<p class="aiou-note">Nh\\u00fang YouTube kh\\u00f4ng kh\\u1ea3 d\\u1ee5ng \\u2014 h\\u00e3y m\\u1edf video b\\u00ean d\\u01b0\\u1edbi.</p>';
            }
            st.kind = 'none';
            setFrame(null, 'none');
            if (linkEl){ linkEl.style.display = 'inline'; }
          }
        }
      });
      st.yt = player;
      st.timer = setInterval(function(){
        if (!player.getCurrentTime) return;
        var ps = player.getPlayerState();
        // While cued/unstarted, getCurrentTime() reads 0 — report the cued
        // keyframe position instead, and keep Pin enabled (only an actual
        // buffer/seek blocks it).
        var raw = player.getCurrentTime() || 0;
        var atRest = (ps === -1 || ps === 5 || ps === 2 || ps === 0);
        var t = window.__aiouNormalizeTime(
          (ps === -1 || ps === 5) ? cfg.start : raw
        );
        // Two clocks on purpose:
        //   paused/cued  -> the reported time IS the shown PTS -> floor
        //                   (matches keyframes.frame_idx exactly at rest)
        //   playing      -> getCurrentTime lags the rendered frame by up to
        //                   half a frame -> Math.round compensates
        // Values stay Estimated either way.
        st.latest = {
          frame: atRest ? Math.floor(t * st.fps) : Math.round(t * st.fps),
          accuracy: 'estimated'
        };
        setFrame(st.latest.frame, 'estimated');
        if (ps === 3 && !st.seeking){ st.seeking = true; pinOff(); }
        if (ps !== 3 && st.seeking){ st.seeking = false; }
      }, 200);
    });
    return;
  }

  // kind === 'none'
  setFrame(null, 'none');
};

// Gradio mounts component HTML via innerHTML, where inline <svg onload>
// handlers are not guaranteed to fire. A MutationObserver boots every player
// node as soon as it appears, regardless of how it was inserted.
function __aiouScan(root){
  var nodes = root.querySelectorAll('svg[data-player]');
  Array.prototype.forEach.call(nodes, function(el){
    if (!el.dataset.booted){ window.__aiouPlayerBoot(el); }
  });
}
window.__aiouScanPlayers = __aiouScan;
function __aiouStartObserver(){
  __aiouScan(document);
  var mo = new MutationObserver(function(muts){
    for (var i = 0; i < muts.length; i++){
      var added = muts[i].addedNodes;
      for (var j = 0; j < added.length; j++){
        var n = added[j];
        if (n.nodeType !== 1) continue;
        if (n.matches && n.matches('svg[data-player]') && !n.dataset.booted){
          window.__aiouPlayerBoot(n);
        } else if (n.querySelectorAll){
          __aiouScan(n);
        }
      }
    }
  });
  mo.observe(document.body || document.documentElement, {childList: true, subtree: true});
}
if (document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', function(){ __aiouStartObserver(); }, {once: true});
} else {
  __aiouStartObserver();
}
"""

_CSS = """
.aiou-player{border:1px solid #ddd;border-radius:8px;padding:10px;margin-top:1rem;text-align:center}
.aiou-player video{width:100%;max-height:60vh}
.aiou-frame-line{font-size:1.05em;font-weight:bold;color:#d00;margin:6px 0}
.aiou-acc{font-weight:normal;color:#666;font-size:0.85em}
.aiou-acc.ok{color:#0a7d32}.aiou-acc.warn{color:#b45309}.aiou-acc.muted{color:#888}
.aiou-note{color:#666;font-style:italic}
"""


def player_head_html() -> str:
    """One-time <head> payload: styles, library functions, YT API loader."""
    return (
        f"<style>{_CSS}</style>"
        f"<script>{_PLAYER_HEAD_JS}{_ACCURACY_LABEL_JS}{_BOOT_JS}</script>"
    )


def _external_link(watch_url: str) -> str:
    safe_url = html.escape(str(watch_url), quote=True)
    return (
        f'<a id="__PID__-link" href="{safe_url}" target="_blank" '
        'rel="noopener noreferrer" style="display:none">'
        "M\u1edf video tr\u00ean YouTube</a>"
    )


def build_player(
    video_id: str,
    *,
    local_path: str | None,
    watch_url: str | None,
    pts_time_sec: float,
    fps: float,
    player_id: str,
    pin_button_id: str | None = None,
) -> str:
    """Render one self-contained player instance for a selected keyframe."""
    kind, source = resolve_player_source(local_path=local_path, watch_url=watch_url)
    safe_video_id = html.escape(str(video_id))
    pid = html.escape(player_id, quote=True)
    start = max(0.0, float(pts_time_sec))

    external = _external_link(watch_url or "").replace("__PID__", pid)

    if kind == "local":
        safe_path = html.escape(str(source), quote=True)
        # The #t= media fragment makes the browser start at the keyframe even
        # before any player JavaScript runs.
        body = (
            f'<video id="{pid}" src="/gradio_api/file={safe_path}#t={start}" '
            f'controls playsinline preload="auto"></video>'
        )
    elif kind == "youtube":
        body = f'<div id="{pid}-yt"></div>'
    else:
        body = '<p class="aiou-note">Kh\u00f4ng c\u00f3 video cho keyframe n\u00e0y \u2014 v\u1eabn ghim \u0111\u01b0\u1ee3c frame.</p>'

    config = {
        "id": player_id,
        "kind": kind,
        "fps": float(fps),
        "start": start,
        "videoId": source if kind == "youtube" else None,
        "pinButtonId": pin_button_id,
    }
    config_json = html.escape(json.dumps(config), quote=True)

    return f"""
    <div class="aiou-player">
        <h3>Video Player: {safe_video_id}</h3>
        <div class="aiou-frame-line">
            Current frame: <span id="{pid}-frame">\u2014</span>
            <span id="{pid}-accuracy" class="aiou-acc muted">Keyframe only</span>
        </div>
        {body}
        <div style="margin-top:6px">{external}</div>
        <svg width="0" height="0" style="position:absolute"
             data-player="{config_json}"
             onload="window.__aiouPlayerBoot && window.__aiouPlayerBoot(this)"></svg>
    </div>
    """
