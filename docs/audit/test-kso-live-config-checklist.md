# Test KSO Live Config Checklist

## Purpose

Safe config checklist for a one-KSO E2E dry run. Defines which sidecar/player
config fields must be configured by the operator BEFORE any physical run (Phase D).

**This is a pre-flight document.** No physical KSO is touched, no X11 render,
no Chromium launch during checklist validation.

## Operator Instructions

Before Phase D (physical run):
1. SSH to KSO (192.168.110.223)
2. Run `sidecar doctor` to verify agent root health
3. Fill all required fields below using `sidecar write-config` / `secret-store-set`
4. Verify with `sidecar config-status` and `sidecar secret-store-check`

## Required Fields

These MUST be configured. All values MUST be filled manually — no automation,
no defaults that contain real credentials.

| Field | Description | How to Set |
|-------|-------------|------------|
| `backend_base_url` | HTTPS URL of Retail Media backend API | `write-config --backend-base-url <url>` |
| `device_code` | KSO device code registered in backend | `write-config --device-code <code>` |
| `device_secret` | Device auth secret | `secret-store-set --stdin < secret.txt` |
| `agent_root` | Absolute path to agent root directory | `init-local-root --root /path/to/root` |

## Optional Fields

These have defaults but SHOULD be verified:

| Field | Default | Description |
|-------|---------|-------------|
| `manifest_poll_interval_sec` | `60` | Seconds between manifest sync |
| `media_cache_path` | `$AGENT_ROOT/media` | Media cache directory |
| `pop_queue_path` | `$AGENT_ROOT/pop/pending` | PoP pending queue |
| `pop_upload_endpoint` | `/api/device-gateway/pop/batch` | PoP batch upload API path |
| `state_file_path` | `$AGENT_ROOT/state/kso_state.json` | KSO state adapter JSON |
| `kill_switch_path` | `$AGENT_ROOT/kill-switch` | Kill-switch marker file |
| `runner_mode` | `once` | `daemon` (continuous) or `once` (single cycle) |
| `display_screen` | `:0` | X11 DISPLAY — for Phase D only |

## Fields That MUST NOT Be Committed

- `backend_base_url` — contains backend hostname
- `device_secret` — authentication secret
- `device_code` — device identifier

These are displayed in the portal /readiness page ONLY as field names,
NEVER as values.

## Backend Readiness Response

```json
{
  "sidecar_config_ready": false,
  "sidecar_config_required_fields": ["backend_base_url", "device_code", "device_secret", "agent_root"],
  "sidecar_config_missing_fields": ["backend_base_url", "device_code", "device_secret", "agent_root"],
  "sidecar_config_checklist": [
    {"name": "backend_base_url", "required": true, "present": false, "filled_by": "operator",
     "description": "HTTPS URL of the Retail Media backend API (e.g. https://api.example.com)"}
  ]
}
```

No values, no URLs, no tokens, no secrets.

## Portal Display

The portal /readiness page shows:
- Field names (visible)
- Required/missing status (✅/❌)
- Filled by: "operator" (always)
- Field descriptions

Never shows:
- Actual `backend_base_url` value
- `device_code` value
- `device_secret` value
- Any token, path, or credential

## Validation Contract

- `sidecar_config_ready` is ALWAYS `false` until operator explicitly confirms
- `sidecar_config_required_fields` lists required field NAMES (not values)
- `sidecar_config_missing_fields` lists which required fields are not configured
- `sidecar_config_checklist` has full field-by-field breakdown (names + status only)
- No config values in ANY response
- No `backend_url`, `token`, `secret`, `device_secret` in JSON or HTML

## Related Documents

- **Operator Runbook:** [test-kso-live-backend-seed-runbook.md](test-kso-live-backend-seed-runbook.md) — Phase A/B/C preflight
- **Readiness Gate:** [one-kso-e2e-dry-run-readiness-gate.md](one-kso-e2e-dry-run-readiness-gate.md)
- **Pilot Plan:** [one-kso-pilot-readiness-plan.md](one-kso-pilot-readiness-plan.md)
