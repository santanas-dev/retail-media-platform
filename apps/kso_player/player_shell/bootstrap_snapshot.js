/**
 * KSO Player Bootstrap Snapshot — default safe hold.
 *
 * DEFAULT snapshot in the immutable shell source directory.
 * In production, the runtime loop will atomically replace this file
 * in the mutable runtime copy — never the installed source.
 *
 * If no runtime writer has run yet, the shell stays in safe hold mode.
 *
 * Safe fields only: schemaVersion, mode, method, payload.
 * NEVER: unsafe aliases, system paths, identifiers, hashes, timestamps.
 */
"use strict";
window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {
  schemaVersion: 1,
  mode: "hold",
  method: "setHold",
  payload: { reason: "hold" }
};
