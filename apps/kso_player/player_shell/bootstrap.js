/**
 * KSO Player Shell Bootstrap — auto-start on page load.
 *
 * Runs after player.js. Checks for a pre-loaded bootstrap snapshot
 * in window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT and applies it, or falls back
 * to safe hold mode.
 *
 * Fully local — no network, no backend, no external URLs.
 * NO dynamic snapshot writer, NO fetch, NO file reads.
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
})();
