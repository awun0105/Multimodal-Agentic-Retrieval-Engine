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

  function beginSeek(s){
    s.seeking = true;
    if (s.pinButton){ s.pinButton.disabled = true; }
  }

  function expectPausedAt(s, target){
    s.pauseAfterSeek = true;
    s.seekTargetTime = target;
    s.seekDeadline = Date.now() + 8000;
  }

  function seekTimeForFrame(frame, fps){
    // Seek to the middle of the frame interval. Seeking to frame / fps can
    // round just below the boundary and make floor(time * fps) show frame - 1.
    return (frame + 0.5) / fps;
  }

  function clampSeekTime(time, duration, fps){
    if (!(duration > 0) || !isFinite(duration)) return Math.max(time, 0);
    var halfFrame = 0.5 / fps;
    return Math.min(Math.max(time, 0), Math.max(duration - halfFrame, 0));
  }

  window.__aiouFrameSnapshot = function(pid){
    var s = window.__aiouPlayers[pid];
    if (!s || !s.latest || s.latest.frame === null || s.latest.frame === undefined){
      return {frame: null, accuracy: 'none', seeking: false};
    }
    return {frame: s.latest.frame, accuracy: s.latest.accuracy, seeking: !!s.seeking};
  };

  window.__aiouSeekFrame = function(pid, rawFrame){
    var s = window.__aiouPlayers[pid];
    var frame = Number(rawFrame);
    if (!s || !(s.fps > 0) || !isFinite(frame) || frame < 0) return false;
    frame = Math.floor(frame);
    var target = seekTimeForFrame(frame, s.fps);

    if (s.kind === 'local'){
      var v = s.video;
      if (!v || !isFinite(v.duration)) return false;
      var localTarget = clampSeekTime(target, v.duration, s.fps);
      beginSeek(s);
      expectPausedAt(s, localTarget);
      v.pause();
      v.currentTime = localTarget;
      return true;
    }
    if (s.kind === 'youtube' && s.yt && s.yt.seekTo){
      var p = s.yt;
      var youtubeTarget = clampSeekTime(
        target, p.getDuration ? p.getDuration() : 0, s.fps
      );
      beginSeek(s);
      expectPausedAt(s, youtubeTarget);
      p.pauseVideo();
      p.seekTo(youtubeTarget, true);
      return true;
    }
    return false;
  };

  window.__aiouStep = function(pid, delta){
    var s = window.__aiouPlayers[pid];
    if (!s || !s.fps) return;
    var stepTime = delta / s.fps;
    if (s.kind === 'local'){
      var v = s.video;
      if (!v || !isFinite(v.duration)) return;
      var dur = Math.max(v.duration - stepTime, 0);
      var nextLocalTime = Math.min(Math.max(v.currentTime + stepTime, 0), dur);
      beginSeek(s);
      expectPausedAt(s, nextLocalTime);
      v.pause();
      v.currentTime = nextLocalTime;
      // seeking flag is raised by the 'seeking' listener; the presented-frame
      // callback clears it, so the shown number follows the real frame.
    } else if (s.kind === 'youtube' && s.yt && s.yt.getCurrentTime){
      var p = s.yt;
      var cur = p.getCurrentTime() || 0;
      var ydur = p.getDuration() || 0;
      var limit = ydur > 0 ? Math.max(ydur - stepTime, 0) : Number.MAX_VALUE;
      var nextYoutubeTime = Math.min(Math.max(cur + stepTime, 0), limit);
      beginSeek(s);
      expectPausedAt(s, nextYoutubeTime);
      p.pauseVideo();
      p.seekTo(nextYoutubeTime, true);
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
  var jumpInput = document.getElementById(pid + '-jump-frame');
  var jumpBtn = document.getElementById(pid + '-jump-btn');

  function label(text, cls){
    if (accEl){ accEl.textContent = text; accEl.className = 'aiou-acc ' + cls; }
  }
  function setFrame(frame, accuracy){
    if (frameEl){ frameEl.textContent = (frame === null || frame === undefined) ? '\\u2014' : String(frame); }
    if (accuracy === 'calculated'){ label('Calculated', 'ok'); }
    else if (accuracy === 'estimated'){ label('Estimated', 'warn'); }
    else { label('Keyframe only', 'muted'); }
    if (pinBtn){ pinBtn.disabled = !!st.seeking; }
  }
  function pinOff(){ if (pinBtn){ pinBtn.disabled = true; } }
  function setJumpEnabled(enabled){
    if (jumpInput){ jumpInput.disabled = !enabled; }
    if (jumpBtn){ jumpBtn.disabled = !enabled; }
  }

  var st = {
    id: pid, kind: cfg.kind, fps: cfg.fps, start: cfg.start,
    latest: {frame: null, accuracy: 'none'},
    seeking: false, raf: null, timer: null, yt: null,
    pauseAfterSeek: false, seekTargetTime: null, seekDeadline: 0,
    pinButton: pinBtn,
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

  function jumpToInputFrame(){
    if (!jumpInput) return;
    var raw = jumpInput.value.trim();
    var frame = Number(jumpInput.value);
    if (raw === '' || !isFinite(frame) || frame < 0 || Math.floor(frame) !== frame){
      jumpInput.setCustomValidity('Frame phải là số nguyên không âm.');
      jumpInput.reportValidity();
      return;
    }
    jumpInput.setCustomValidity('');
    jumpInput.value = String(Math.floor(frame));
    window.__aiouSeekFrame(pid, frame);
  }
  if (jumpBtn){ listen(jumpBtn, 'click', jumpToInputFrame); }
  if (jumpInput){
    listen(jumpInput, 'input', function(){ jumpInput.setCustomValidity(''); });
    listen(jumpInput, 'keydown', function(ev){
      if (ev.key === 'Enter'){ ev.preventDefault(); jumpToInputFrame(); }
    });
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
      if (st.pauseAfterSeek){
        v.pause();
        st.pauseAfterSeek = false;
        st.seekTargetTime = null;
      }
      if (hasRVFC){ st.raf = v.requestVideoFrameCallback(present); }
    };
    var onSeekStart = function(){
      st.seeking = true; pinOff();
    };
    var onSeekEndFallback = function(){
      if (hasRVFC) return; // the presented callback owns re-enabling
      var t = window.__aiouNormalizeTime(v.currentTime);
      st.latest = {frame: Math.floor(t * st.fps), accuracy: 'estimated'};
      st.seeking = false;
      if (st.pauseAfterSeek){
        v.pause();
        st.pauseAfterSeek = false;
        st.seekTargetTime = null;
      }
      setFrame(st.latest.frame, 'estimated');
    };
    listen(v, 'seeking', onSeekStart);
    listen(v, 'seeked', onSeekEndFallback);
    listen(v, 'error', function(){
      st.kind = 'none';
      setJumpEnabled(false);
      setFrame(null, 'none');
      if (linkEl){ linkEl.style.display = 'inline'; }
    });
    listen(v, 'loadedmetadata', function(){
      setJumpEnabled(true);
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
    setJumpEnabled(v.readyState >= 1);
    if (cfg.start > 0){ try { v.currentTime = cfg.start; } catch (e) {} }
    if (hasRVFC){ st.raf = v.requestVideoFrameCallback(present); }
    else { setFrame(Math.floor(window.__aiouNormalizeTime(cfg.start) * st.fps), 'estimated'); }
    return;
  }

  if (cfg.kind === 'youtube'){
    setFrame(null, 'estimated');
    pinOff();
    window.__aiouEnsureYT(function(){
      var holder = document.getElementById(pid + '-yt');
      if (!holder) return;
      var initialLoad = true;
      var loadRequested = false;
      var mutedForLoad = false;

      function publishCurrentFrame(target){
        var loaded = target.getVideoLoadedFraction ? target.getVideoLoadedFraction() : 0;
        var raw = Number(target.getCurrentTime());
        if (!(loaded > 0) || !isFinite(raw)) return false;
        var t = window.__aiouNormalizeTime(raw);
        st.latest = {
          frame: Math.floor(t * st.fps),
          accuracy: 'estimated'
        };
        st.seeking = false;
        setFrame(st.latest.frame, 'estimated');
        return true;
      }

      function finishInitialLoad(target){
        if (!initialLoad || !publishCurrentFrame(target)) return;
        initialLoad = false;
        target.pauseVideo();
        if (mutedForLoad && target.unMute){ target.unMute(); }
      }

      var player = new YT.Player(holder, {
        playerVars: {rel: 0, modestbranding: 1, playsinline: 1, autoplay: 0},
        events: {
          onReady: function(ev){
            // A muted load requests actual media at the fractional timestamp.
            // The first PLAYING event is paused immediately; only the resulting
            // PAUSED time is exposed as Current frame.
            st.seeking = true;
            pinOff();
            setJumpEnabled(true);
            if (ev.target.mute){ ev.target.mute(); mutedForLoad = true; }
            loadRequested = true;
            ev.target.loadVideoById({
              videoId: cfg.videoId,
              startSeconds: Math.max(cfg.start, 0)
            });
          },
          onStateChange: function(ev){
            if (!loadRequested || !initialLoad) return;
            if (ev.data === 1){
              ev.target.pauseVideo();
            } else if (ev.data === 2){
              finishInitialLoad(ev.target);
            }
          },
          onError: function(){
            if (st.timer){ clearInterval(st.timer); st.timer = null; }
            if (holder && holder.parentNode){
              holder.parentNode.innerHTML =
                '<p class="aiou-note">Nh\\u00fang YouTube kh\\u00f4ng kh\\u1ea3 d\\u1ee5ng \\u2014 h\\u00e3y m\\u1edf video b\\u00ean d\\u01b0\\u1edbi.</p>';
            }
            st.kind = 'none';
            if (jumpInput){ jumpInput.disabled = true; }
            if (jumpBtn){ jumpBtn.disabled = true; }
            setFrame(null, 'none');
            if (linkEl){ linkEl.style.display = 'inline'; }
          }
        }
      });
      st.yt = player;
      st.timer = setInterval(function(){
        if (!player.getCurrentTime) return;
        var ps = player.getPlayerState();
        if (initialLoad){
          if (loadRequested && ps === 1){ player.pauseVideo(); }
          else if (loadRequested && ps === 2){ finishInitialLoad(player); }
          return;
        }
        if (ps === 3){
          if (!st.seeking){ beginSeek(st); }
          return;
        }
        if (st.pauseAfterSeek && ps === 1){
          player.pauseVideo();
          return;
        }
        var raw = Number(player.getCurrentTime());
        if (!isFinite(raw)) return;
        if (st.pauseAfterSeek && st.seekTargetTime !== null){
          var tolerance = Math.max(2 / st.fps, 0.25);
          var targetReached = Math.abs(raw - st.seekTargetTime) <= tolerance;
          if (!targetReached && Date.now() < st.seekDeadline) return;
          if (ps !== 2 && ps !== 5){
            player.pauseVideo();
            return;
          }
          st.pauseAfterSeek = false;
          st.seekTargetTime = null;
        }
        var t = window.__aiouNormalizeTime(raw);
        // Field calibration on the L-series batch: the YouTube readout ran
        // exactly +1 against keyframes.frame_idx when Math.round was used
        // during playback, so floor is applied uniformly here. Values stay
        // Estimated — getCurrentTime() has no ground truth guarantee.
        st.latest = {
          frame: Math.floor(t * st.fps),
          accuracy: 'estimated'
        };
        if (st.seeking){ st.seeking = false; }
        setFrame(st.latest.frame, 'estimated');
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
.aiou-player{box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:6px;padding:8px;margin:0;text-align:center;overflow:hidden}
.aiou-media{box-sizing:border-box;width:100%;aspect-ratio:16/9;background:#000;overflow:hidden;display:flex;align-items:center;justify-content:center}
.aiou-media video,.aiou-media iframe,.aiou-media>div{display:block;width:100%!important;height:100%!important;max-width:100%!important;max-height:100%!important;border:0;object-fit:contain}
.aiou-media.empty{aspect-ratio:auto;min-height:100px;background:#f3f4f6;padding:12px}
.aiou-frame-line{font-size:1.05em;font-weight:bold;color:#d00;margin:6px 0}
.aiou-frame-jump{display:flex;align-items:center;justify-content:center;gap:6px;margin:8px 0 2px;flex-wrap:wrap}
.aiou-frame-jump input{box-sizing:border-box!important;width:132px!important;min-width:132px!important;height:32px!important;min-height:32px!important;padding:3px 8px!important;border:1px solid var(--input-border-color,#6b7280)!important;border-radius:var(--input-radius,5px)!important;background:var(--input-background-fill,#374151)!important;color:var(--body-text-color,#f9fafb)!important;-webkit-text-fill-color:var(--body-text-color,#f9fafb)!important;font-size:14px!important;line-height:1.2!important}
.aiou-frame-jump input:focus{background:var(--input-background-fill-focus,var(--input-background-fill,#374151))!important;border-color:var(--input-border-color-focus,var(--color-accent,#f97316))!important;outline:none!important}
.aiou-frame-jump input::placeholder{color:var(--input-placeholder-color,#d1d5db)!important;-webkit-text-fill-color:var(--input-placeholder-color,#d1d5db)!important;opacity:1!important}
.aiou-frame-jump button{box-sizing:border-box!important;height:32px!important;min-height:32px!important;padding:3px 10px!important;border:1px solid var(--button-primary-border-color,#ea580c)!important;border-radius:var(--button-large-radius,5px)!important;background:var(--button-primary-background-fill,#f97316)!important;color:var(--button-primary-text-color,#fff)!important;-webkit-text-fill-color:var(--button-primary-text-color,#fff)!important;font-size:13px!important;font-weight:600!important;line-height:1.2!important;cursor:pointer}
.aiou-frame-jump button:hover{background:var(--button-primary-background-fill-hover,#ea580c)!important}
.aiou-frame-jump button:disabled,.aiou-frame-jump input:disabled{cursor:not-allowed;opacity:.55}
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
            '<div class="aiou-media">'
            f'<video id="{pid}" src="/gradio_api/file={safe_path}#t={start}" '
            f'controls playsinline preload="auto"></video>'
            "</div>"
        )
    elif kind == "youtube":
        body = f'<div class="aiou-media"><div id="{pid}-yt"></div></div>'
    else:
        body = (
            '<div class="aiou-media empty"><p class="aiou-note">'
            "Kh\u00f4ng c\u00f3 video cho keyframe n\u00e0y \u2014 "
            "v\u1eabn ghim \u0111\u01b0\u1ee3c frame.</p></div>"
        )

    config = {
        "id": player_id,
        "kind": kind,
        "fps": float(fps),
        "start": start,
        "videoId": source if kind == "youtube" else None,
        "pinButtonId": pin_button_id,
    }
    config_json = html.escape(json.dumps(config), quote=True)
    # Enabled by the boot runtime only after the selected media can seek.
    jump_disabled = " disabled"

    return f"""
    <div class="aiou-player">
        <h3>Video Player: {safe_video_id}</h3>
        <div class="aiou-frame-line">
            Current frame: <span id="{pid}-frame">\u2014</span>
            <span id="{pid}-accuracy" class="aiou-acc muted">Keyframe only</span>
        </div>
        {body}
        <div class="aiou-frame-jump">
            <input id="{pid}-jump-frame" type="number" min="0" step="1"
                   inputmode="numeric" placeholder="Nhập frame"
                   aria-label="Nhảy tới frame"{jump_disabled}>
            <button id="{pid}-jump-btn" type="button"{jump_disabled}>Đi tới Frame</button>
        </div>
        <div style="margin-top:6px">{external}</div>
        <svg width="0" height="0" style="position:absolute"
             data-player="{config_json}"
             onload="window.__aiouPlayerBoot && window.__aiouPlayerBoot(this)"></svg>
    </div>
    """
