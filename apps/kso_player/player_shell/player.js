/**
 * KSO Player Shell — minimal JavaScript API for Chromium kiosk.
 *
 * Modes: hold (ads blocked), render (ad ready to display).
 * Fully local — no network, no remote services, no external URLs.
 *
 * Public API:
 *   window.KsoPlayerShell.setHold(reason)
 *   window.KsoPlayerShell.setRenderPlan(plan)
 *   window.KsoPlayerShell.clear()
 *   window.KsoPlayerShell.applySnapshot(snapshot)
 *   window.KsoPlayerShell.startLiveSnapshotRefresh(intervalMs)
 *   window.KsoPlayerShell.stopLiveSnapshotRefresh()
 *
 * Plan accepts only safe fields:
 *   { mediaType: "image"|"video", durationBucket: "...",
 *     mediaRef: "media/current/slot-000" }
 *
 * Media is rendered via safe DOM API only (document.createElement).
 * NEVER: unsafe HTML injection, dynamic code execution, network requests.
 * NEVER accepts: absolute paths, names, IDs, hash data, auth data.
 */
(function () {
  "use strict";

  /* ── DOM references ──────────────────────────────────────────────── */

  var holdScreen = document.getElementById("kso-hold");
  var holdText = document.getElementById("kso-hold-text");
  var renderScreen = document.getElementById("kso-render");
  var renderText = document.getElementById("kso-render-text");
  var mediaSlot = document.getElementById("kso-media-slot");

  /* ── Active screen tracking ──────────────────────────────────────── */

  var activeScreen = null;
  var currentPlan = null;

  /* ── Safe reason labels ──────────────────────────────────────────── */

  var SAFE_REASONS = {
    hold: "Advertising temporarily unavailable",
    render: "Playing",
  };

  function safeReason(raw) {
    if (typeof raw !== "string" || !raw.trim()) {
      return "hold";
    }
    var trimmed = raw.trim().toLowerCase();
    if (SAFE_REASONS.hasOwnProperty(trimmed)) {
      return trimmed;
    }
    return "hold";
  }

  /* ── Media slot helpers ────────────────────────────────────────── */

  /**
   * Clear the media slot — remove all child elements safely.
   * Uses replaceChildren() for safe DOM manipulation.
   */
  function _clearMediaSlot() {
    if (mediaSlot) {
      mediaSlot.replaceChildren();
    }
  }

  /**
   * Validate that a mediaRef is safe for use as src.
   * Whitelist: only a-z, 0-9, /, _, -
   * No: .., ~, \\, ://, file:, http:, https:, %2e, %2f
   */
  var _MEDIA_REF_RE = /^[a-z0-9\/_-]+$/;
  var _UNSAFE_IN_REF = ["..", "~", "\\", "://", "file:", "http:", "https:",
                         "%2e", "%2f", "%2E", "%2F"];

  function _isMediaRefSafe(ref) {
    if (typeof ref !== "string" || !ref.trim()) {
      return false;
    }
    var mref = ref.trim();
    if (!_MEDIA_REF_RE.test(mref)) {
      return false;
    }
    var lower = mref.toLowerCase();
    for (var i = 0; i < _UNSAFE_IN_REF.length; i++) {
      if (lower.indexOf(_UNSAFE_IN_REF[i]) !== -1) {
        return false;
      }
    }
    return true;
  }

  /* ── Screen switching ────────────────────────────────────────────── */

  function showScreen(screen) {
    if (activeScreen === screen) return;
    // Hide all
    if (holdScreen) holdScreen.classList.remove("kso-active");
    if (renderScreen) renderScreen.classList.remove("kso-active");
    // Show target
    if (screen) {
      screen.classList.add("kso-active");
    }
    activeScreen = screen;
  }

  /* ── Public API ──────────────────────────────────────────────────── */

  /**
   * Set hold mode — ads are blocked.
   * @param {string} reason — safe reason (only "hold" is displayed).
   */
  function setHold(reason) {
    var r = safeReason(reason);
    if (holdText) {
      holdText.textContent = SAFE_REASONS[r] || SAFE_REASONS.hold;
    }
    showScreen(holdScreen);
    currentPlan = null;
  }

  /**
   * Set render mode — ad is ready to display.
   * Creates <img> or <video> via safe DOM API (document.createElement).
   * @param {object} plan — safe plan with mediaType, durationBucket, and
   *   optionally mediaRef (safe local alias only, no paths).
   */
  function setRenderPlan(plan) {
    if (!plan || typeof plan !== "object") {
      setHold();
      return;
    }

    var mediaType = (typeof plan.mediaType === "string")
      ? plan.mediaType.trim().toLowerCase()
      : "unknown";
    var durationBucket = (typeof plan.durationBucket === "string")
      ? plan.durationBucket.trim().toLowerCase()
      : "unknown";

    // Only image and video are supported
    if (mediaType !== "image" && mediaType !== "video") {
      setHold();
      return;
    }

    // Validate mediaRef safety before using as src
    var mediaRef = (typeof plan.mediaRef === "string" && plan.mediaRef.trim())
      ? plan.mediaRef.trim()
      : "";
    if (mediaRef && !_isMediaRefSafe(mediaRef)) {
      setHold();
      return;
    }

    currentPlan = {
      mediaType: mediaType,
      durationBucket: durationBucket,
    };
    if (mediaRef) {
      currentPlan.mediaRef = mediaRef;
    }

    // Clear existing media and create new element via safe DOM API
    _clearMediaSlot();

    if (mediaRef) {
      var el;
      if (mediaType === "image") {
        el = document.createElement("img");
        el.setAttribute("src", mediaRef);
        el.setAttribute("alt", "");
      } else {
        el = document.createElement("video");
        el.setAttribute("src", mediaRef);
        el.setAttribute("muted", "");
        el.setAttribute("autoplay", "");
        el.setAttribute("loop", "");
        el.setAttribute("playsinline", "");
      }
      if (mediaSlot && el) {
        mediaSlot.appendChild(el);
      }
    }

    if (renderText) {
      var label = mediaType.charAt(0).toUpperCase() + mediaType.slice(1);
      renderText.textContent = label + " \u2014 " + durationBucket;
    }

    showScreen(renderScreen);
  }

  /**
   * Clear — reset to neutral hold state.
   */
  function clear() {
    currentPlan = null;
    _clearMediaSlot();
    if (holdText) {
      holdText.textContent = SAFE_REASONS.hold;
    }
    if (renderText) {
      renderText.textContent = "";
    }
    showScreen(holdScreen);
  }

  /* ── Live snapshot refresh ──────────────────────────────────────── */

  var _liveRefreshInterval = null;
  var DEFAULT_REFRESH_INTERVAL_MS = 5000;  // 5 seconds

  /**
   * Load the latest bootstrap_snapshot.js via <script> injection.
   * Cache-busting prevents stale copies. On load → applySnapshot.
   * On error → safe hold (no crash, no error leakage).
   *
   * NEVER uses fetch/XHR/WebSocket. Only local <script> tag.
   */
  function _refreshLiveSnapshot() {
    var script = document.createElement("script");
    // Cache-bust with timestamp — same-origin, CSP: script-src 'self'
    script.src = "bootstrap_snapshot.js?ts=" + Date.now();
    script.onload = function () {
      try {
        var snap = window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT;
        if (snap && typeof snap === "object") {
          applySnapshot(snap);
        }
      } catch (_e) {
        // Safe hold — never expose errors
        setHold("hold");
      }
      // Clean up script tag
      if (script && script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
    script.onerror = function () {
      // Script load error → safe hold, no crash
      if (script && script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
    document.head.appendChild(script);
  }

  /**
   * Start periodic live snapshot refresh.
   * @param {number} [intervalMs] — refresh interval in ms (default 5000).
   */
  function startLiveSnapshotRefresh(intervalMs) {
    if (_liveRefreshInterval !== null) {
      return;  // Already running
    }
    var interval = (typeof intervalMs === "number" && intervalMs >= 1000)
      ? intervalMs
      : DEFAULT_REFRESH_INTERVAL_MS;
    _liveRefreshInterval = setInterval(_refreshLiveSnapshot, interval);
  }

  /**
   * Stop periodic live snapshot refresh.
   */
  function stopLiveSnapshotRefresh() {
    if (_liveRefreshInterval !== null) {
      clearInterval(_liveRefreshInterval);
      _liveRefreshInterval = null;
    }
  }

  /* ── Export ──────────────────────────────────────────────────────── */

  function applySnapshot(snapshot) {
    // Validate schema structure
    if (!snapshot || typeof snapshot !== "object") {
      setHold("hold");
      return;
    }
    if (typeof snapshot.schemaVersion !== "number" || snapshot.schemaVersion < 1) {
      setHold("hold");
      return;
    }

    var mode = snapshot.mode;
    var method = snapshot.method;
    var payload = snapshot.payload;

    // Mode must be "hold" or "render"
    if (mode !== "hold" && mode !== "render") {
      setHold("hold");
      return;
    }

    // Method must match mode
    if (mode === "hold" && method !== "setHold") {
      setHold("hold");
      return;
    }
    if (mode === "render" && method !== "setRenderPlan") {
      setHold("hold");
      return;
    }

    // Hold path
    if (mode === "hold") {
      setHold("hold");
      return;
    }

    // Render path — validate payload
    if (!payload || typeof payload !== "object") {
      setHold("hold");
      return;
    }

    // Only accept safe payload keys
    var mediaType = (typeof payload.mediaType === "string")
      ? payload.mediaType.trim().toLowerCase()
      : "unknown";
    var durationBucket = (typeof payload.durationBucket === "string")
      ? payload.durationBucket.trim().toLowerCase()
      : "unknown";

    // Only accept safe payload keys (mediaRef optional for render)
    var allowedKeys = {mediaType: true, durationBucket: true, mediaRef: true};
    var hasExtraKeys = false;
    for (var k in payload) {
      if (payload.hasOwnProperty(k) && !allowedKeys[k]) {
        hasExtraKeys = true;
        break;
      }
    }
    if (hasExtraKeys) {
      setHold("hold");
      return;
    }

    // Validate mediaRef if present (safe local alias only)
    if (typeof payload.mediaRef === "string" && payload.mediaRef.trim()) {
      var mref = payload.mediaRef.trim();
      // Whitelist: only a-z, 0-9, /, _, -
      if (!/^[a-z0-9\/_-]+$/.test(mref)) {
        setHold("hold");
        return;
      }
      // Reject unsafe substrings
      var unsafeInRef = ["..", "~", "\\\\", "://", "file:", "http:", "https:",
                         "%2e", "%2f", "%2E", "%2F"];
      var mrefLower = mref.toLowerCase();
      for (var ui = 0; ui < unsafeInRef.length; ui++) {
        if (mrefLower.indexOf(unsafeInRef[ui]) !== -1) {
          setHold("hold");
          return;
        }
      }
    }

    setRenderPlan({
      mediaType: mediaType,
      durationBucket: durationBucket,
      mediaRef: (typeof payload.mediaRef === "string" && payload.mediaRef.trim())
        ? payload.mediaRef.trim()
        : undefined,
    });
  }

  /* ── Export ──────────────────────────────────────────────────────── */

  window.KsoPlayerShell = {
    setHold: setHold,
    setRenderPlan: setRenderPlan,
    clear: clear,
    applySnapshot: applySnapshot,
    startLiveSnapshotRefresh: startLiveSnapshotRefresh,
    stopLiveSnapshotRefresh: stopLiveSnapshotRefresh,
  };

  /* ── Initial state ───────────────────────────────────────────────── */

  clear();
})();
