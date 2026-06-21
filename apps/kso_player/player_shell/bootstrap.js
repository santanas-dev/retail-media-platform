/**
 * KSO Player Shell Bootstrap — auto-start on page load.
 *
 * Runs after player.js. Checks for a pre-loaded bootstrap snapshot
 * in window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT and applies it, or falls back
 * to safe hold mode.
 *
 * After initial bootstrap, starts live snapshot refresh so the shell
 * can pick up new snapshots without a page reload.
 *
 * Fully local — no network, no backend, no external URLs.
 * Live refresh uses only local <script> tag injection with cache-busting.
 */
(function () {
  "use strict";

  var shell = window.KsoPlayerShell;
  if (!shell) {
    // Player shell not loaded — cannot proceed
    return;
  }

  var snapshot = window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT;

  if (snapshot && typeof snapshot === "object") {
    // applySnapshot does full validation internally
    shell.applySnapshot(snapshot);
  } else {
    // No bootstrap snapshot — safe fallback to hold
    shell.setHold("hold");
  }

  // ── Start live snapshot refresh ────────────────────────────────
  // Default interval: 5000ms. The runtime loop writes new snapshots
  // to bootstrap_snapshot.js atomically. The shell picks them up
  // via periodic <script> tag injection with cache-busting.
  // NO fetch, NO XHR, NO WebSocket, NO external URLs.
  if (shell.startLiveSnapshotRefresh) {
    shell.startLiveSnapshotRefresh(5000);
  }
})();
