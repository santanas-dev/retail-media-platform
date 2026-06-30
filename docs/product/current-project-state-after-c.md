# Current Project State — After Phase C (Device Gateway)

> **Дата:** 2026-07-01
> **Commit:** C.5 closure
> **GitHub:** `santanas-dev/retail-media-platform` (private)

---

## Что закрыто

### Phase A (Multichannel Core Foundation) — ✅ COMPLETED
- A.2 ERD/API/Event Contracts v2.5
- A.3 KSO Data Migration (schema + data, legacy preserved)

### Phase B (Channel Orchestrator + Universal Manifest) — ✅ COMPLETED
- B.1 Channel Registry Cleanup
- B.2 Device Model Unification
- B.3 Placement (schema, service, API, portal visibility)
- B.4 Channel Orchestrator (contracts, mock adapter, service, simulation)
- B.5 Universal Manifest (schema, builder, validation, compatibility analysis)

### Phase C (Device Gateway) — ✅ COMPLETED
- C.0 Pre-C Design Gate
- C.1 Universal Manifest Device Gateway Delivery
- C.1.1 Security & Regression Gate
- C.2 Device Registration Validation
- C.3 Heartbeat / Device Status Validation
- C.4 Manifest Pull Dry-Run / Delivery Validation
- C.5 Closure Gate

---

## Backend Baseline

| Параметр | Значение |
|---|---|
| Collected | 1426 |
| Passed | 1360 |
| Failed (pre-existing) | 66 |
| Collection errors | 0 |
| Gateway Suite (C.1–C.4) | 195/195 |

---

## Portal Baseline

| Параметр | Значение |
|---|---|
| Portal tests | 863 passed / 0 failed / 32 skipped |
| Последнее изменение | B.3.4 (Placement portal visibility) |

---

## Gateway Endpoint Inventory

- **15 device endpoints** (JWT auth): auth, me, heartbeat, config, 3 manifest, 2 PoP, 3 media, manifest apply, cache report
- **11 admin endpoints** (user permissions): devices CRUD, credentials, heartbeats, events, logs
- **Universal Manifest** endpoint: `/manifest/universal/current` (dry-run/preview)

---

## Production KSO Flow

- Legacy KSO manifest delivery через `GeneratedManifest` — **сохранён и не тронут**
- Publication flow, `generate_manifests()`, `publish_batch()` — **не менялись**
- KSO projection — **не менялась**

---

## Что работает как preview/dry-run

- UniversalManifestV1 построение через Orchestrator chain
- Universal manifest delivery через Device Gateway (device JWT auth)
- ETag/304 для universal manifest
- Structured no_manifest responses

---

## Deferred Items

| Item | Причина |
|---|---|
| mTLS | Future hardening |
| Final signed manifest | B.6 (Manifest Signing) |
| Universal manifest storage | B.6 |
| Real publish (universal) | Phase D/E |
| KSO Adapter | Phase D+ |
| Compatibility projection | Phase E |
| PoP analytics (ClickHouse) | Phase F |
| Rate limiting / replay protection | Security hardening |
| Certificate lifecycle | mTLS deferred |
| Device heartbeat staleness detection | Cron/background task |
| Device auto-retirement | Policy |

---

## Следующий этап

**Phase D (D.0 — Inventory / Planning Design Gate).**

Требуется design gate для следующего набора функций:
- KSO Adapter (channel-specific)
- Universal manifest storage
- Real publish pipeline
- API integration
