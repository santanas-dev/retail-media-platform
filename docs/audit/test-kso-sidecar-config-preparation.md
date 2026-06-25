# Test KSO Sidecar Config — Phase B Preparation

> **Step:** 38.9  
> **Date:** 2026-06-26  
> **Status:** 📋 Phase B preparation (no physical KSO actions)  
> **ВАЖНО:** This is a PREPARATION document. No SSH, no KSO access, no physical run.

---

## 1. Config Mechanisms (анализ)

### 1.1 Agent Config

**File:** `config/agent_config.json` (in agent root)

| Field | Required | Type | Validation |
|---|---|---|---|
| `backend_base_url` | ✅ | `http(s)://host` | No username/password/query params; no forbidden substrings |
| `device_code` | ✅ | `[a-zA-Z0-9._-]{3,64}` | No forbidden substrings |
| `tls_verify` | ❌ | `bool` | Default: `true` |
| `request_timeout_sec` | ❌ | `int (1–120)` | Default: `10` |
| `local_interface_version` | ❌ | `"1.0"` | Only `"1.0"` allowed |

**Forbidden substrings in field values:** `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`, `payment_card`, `receipt`, `local_path`, `file_path`

### 1.2 Device Secret

**File:** `config/device_secret.dev` (in agent root)

- Stored via `secret-store-set` — **stdin only**, never CLI args
- Length: 16–512 chars
- Permissions: `0600`
- **Never logged, never printed, never in JSON output**
- Dev-mode gate: `--dev-secret-store` flag or `KSO_DEV_SECRET_STORE=1` env

### 1.3 Agent Root Structure

```
<AGENT_ROOT>/
├── config/                  # agent_config.json, device_secret.dev
├── state/                   # kso_state.json (from KSO state adapter)
├── manifest/                # current_manifest.json (synced from backend)
├── media/                   # media/current/ (cached media files)
│   └── current/
├── pop/                     # PoP pending queue (JSONL)
│   └── pending/
├── runtime_config/          # server-provided runtime config
│   └── config.json
├── logs/                    # agent logs
├── agent_status.json        # agent health/readiness status
└── kill-switch              # marker file — presence stops all activity
```

### 1.4 CLI Commands (config-related)

| Command | Purpose | Safe output |
|---|---|---|
| `init-local-root --root <AGENT_ROOT>` | Create folder structure + agent_status.json | Path only |
| `write-config --root <AGENT_ROOT>` | Write/update config | Prompts via stdin |
| `config-status --root <AGENT_ROOT>` | Show config health | Shows hostname, NOT value |
| `secret-store-set --root <AGENT_ROOT>` | Write secret | **stdin only** — no output |
| `secret-store-check --root <AGENT_ROOT>` | Check secret store | `present`, `permissions_ok` — **never value** |
| `doctor --root <AGENT_ROOT>` | Full health check | All fields except secret value |

### 1.5 Manifest Fetch & PoP Upload

- **Manifest:** `sync-manifest` → `device_auth_client` → `GET /api/device-gateway/manifest` → save to `manifest/current_manifest.json`
- **PoP:** `pop_rotation_apply` → reads JSONL from `pop/pending/` → `POST /api/device-gateway/pop/batch`
- Both use `HttpClientConfig(base_url=...)` from `agent_config.json`

---

## 2. Safe Config Template

**File:** `apps/kso_sidecar_agent/config/agent_config.json.example`

```json
{
  "backend_base_url": "<TEST_BACKEND_BASE_URL>",
  "device_code": "<TEST_KSO_DEVICE_CODE>",
  "tls_verify": true,
  "request_timeout_sec": 10,
  "local_interface_version": "1.0"
}
```

### Operator instructions (template header)

1. Copy to `config/agent_config.json` (NOT tracked by git)
2. Replace each `<...>` placeholder with the real value
3. Run `sidecar config-status --root <AGENT_ROOT>` to verify
4. Create `device_secret.dev` via `secret-store-set` (stdin only)
5. **NEVER commit** `agent_config.json` or `device_secret.dev`

---

## 3. Gitignore Protection

Added to `.gitignore`:

```
apps/kso_sidecar_agent/config/agent_config.json        # filled config
apps/kso_sidecar_agent/config/device_secret.dev         # secret store
apps/kso_sidecar_agent/config/*_filled.json             # any filled variant
agent-root/ kso-agent-root/ test-agent-root/            # local test roots
```

**Allowed in git:**
- `config/agent_config.json.example` — template with placeholders ✅
- `config/` directory structure — empty dir is fine ✅

---

## 4. Config Validation & Dry-Check

### 4.1 `config_status()` — enhanced

Now returns `has_placeholders` and `placeholder_fields`:

```python
{
    "present": True,
    "ok": True,
    "backend_scheme": "https",
    "backend_host": "...",       # hostname only, NOT full URL
    "device_code": "...",        # present but may be placeholder
    "tls_verify": True,
    "has_placeholders": True,    # ⬅ NEW: True if values are templates
    "placeholder_fields": [      # ⬅ NEW: which fields are placeholders
        "backend_base_url",
        "device_code"
    ]
}
```

### 4.2 `validate_no_placeholders()` — NEW

Returns safe summary WITHOUT values:

```python
{
    "present": True,             # file exists
    "ok": True,                  # valid JSON + schema
    "filled": False,             # True = all placeholders replaced
    "placeholder_fields": [...],
    "all_required_present": False
}
```

**Placeholder detection patterns:**
- `<TEST_BACKEND_BASE_URL>`, `<TEST_KSO_DEVICE_CODE>`, `<DEVICE_SECRET_VALUE>`, `<AGENT_ROOT>`
- `<REPLACE_ME>`, `changeme`, `placeholder`

---

## 5. Readiness Contract

### 5.1 `sidecar_config_ready`

Backend readiness always returns `sidecar_config_ready: false` because:
- The backend **cannot** inspect the sidecar's local filesystem
- Only the sidecar's `validate_no_placeholders()` can determine config readiness
- When Phase B is executed on the actual KSO, `sidecar doctor` output will confirm config state

### 5.2 Safety

- ✅ Readiness output still does NOT show config values
- ✅ Only field NAMES appear in `sidecar_config_required_fields` and `sidecar_config_missing_fields`
- ✅ `sidecar_config_checklist` shows names + descriptions — no values
- ✅ `device_secret` mentioned only as a required field name
- ✅ Phase D remains ⛔ blocked

---

## 6. Operator Phase B Checklist (PREPARATION ONLY)

| # | Step | Command | Safe? |
|---|---|---|---|
| B1 | Copy template | `cp agent_config.json.example agent_config.json` | ✅ |
| B2 | Fill base URL | Edit `agent_config.json` → replace `<TEST_BACKEND_BASE_URL>` | ⚠️ private |
| B3 | Fill device code | Edit `agent_config.json` → replace `<TEST_KSO_DEVICE_CODE>` | ⚠️ private |
| B4 | Write secret | `echo -n '<SECRET>' | sidecar secret-store-set --root <AGENT_ROOT>` | ✅ stdin |
| B5 | Verify config | `sidecar config-status --root <AGENT_ROOT>` | ✅ safe output |
| B6 | Verify secret | `sidecar secret-store-check --root <AGENT_ROOT>` | ✅ safe output |
| B7 | Dry-check filled | `sidecar validate-no-placeholders --root <AGENT_ROOT>` | ✅ safe output |
| B8 | Full doctor | `sidecar doctor --root <AGENT_ROOT>` | ✅ safe output |

---

## 7. What is NOT Done (38.9)

- ❌ No SSH to KSO 192.168.110.223
- ❌ No sidecar `init-local-root` / `write-config` / `secret-store-set` execution
- ❌ No manifest fetch / PoP upload
- ❌ No X11 / Chromium / physical run
- ❌ No UKM5/Openbox/systemd modification
- ❌ No real values committed to git

---

## 8. Live Blockers (после 38.9)

| # | Blocker | Phase |
|---|---|---|
| 1 | Config не заполнен на КСО (placeholder values) | B |
| 2 | Secret не записан на КСО | B |
| 3 | Media cache пуст | C |
| 4 | Phase D manual approval | D |

## 9. Controlled Application Preflight

When Phase B is approved for execution, follow the controlled procedure in:

→ **`test-kso-sidecar-config-application-preflight.md`**

Includes: step-by-step commands (templates), safety gates, stop criteria, rollback, запрещённые действия.
