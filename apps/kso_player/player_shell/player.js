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
 *
 * Plan accepts only safe fields:
 *   { mediaType: "image"|"video", durationBucket: "short"|"medium"|"long"|"unknown" }
 *
 * NEVER accepts: absolute paths, names, IDs, hash data, auth data.
 */
(function () {
  "use strict";

  /* ── DOM references ──────────────────────────────────────────────── */

  var holdScreen = document.getElementById("kso-hold");
  var holdText = document.getElementById("kso-hold-text");
  var renderScreen = document.getElementById("kso-render");
  var renderText = document.getElementById("kso-render-text");

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
   * @param {object} plan — safe plan with mediaType and durationBucket.
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

    currentPlan = {
      mediaType: mediaType,
      durationBucket: durationBucket,
    };

    if (renderText) {
      var label = mediaType.charAt(0).toUpperCase() + mediaType.slice(1);
      renderText.textContent = label + " — " + durationBucket;
    }

    showScreen(renderScreen);
  }

  /**
   * Clear — reset to neutral hold state.
   */
  function clear() {
    currentPlan = null;
    if (holdText) {
      holdText.textContent = SAFE_REASONS.hold;
    }
    if (renderText) {
      renderText.textContent = "";
    }
    showScreen(holdScreen);
  }

  /* ── Export ──────────────────────────────────────────────────────── */

  window.KsoPlayerShell = {
    setHold: setHold,
    setRenderPlan: setRenderPlan,
    clear: clear,
  };

  /* ── Initial state ───────────────────────────────────────────────── */

  clear();
})();
