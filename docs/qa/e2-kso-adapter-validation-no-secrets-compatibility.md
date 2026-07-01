# E.2 — KSO Adapter Validation + No-Secrets / Compatibility Gate

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## Что проверено

### 1. No-Secrets Validation

FORBIDDEN_SECRET_WORDS расширен с 12 до 20 слов:
```
password, passwd, pwd,
secret, client_secret,
token, access_token, refresh_token,
api_key, access_key, private_key,
authorization, bearer,
signed_url, signature,
credential, credentials,
cookie, session, jwt
```

Добавлен `ALLOWED_SAFE_KEYS = {"signature_status"}` — ключи в этом списке не флажатся,
даже если содержат forbidden-подстроку (например, `signature_status` содержит `signature`).

`_recursive_check_forbidden()` проверяет рекурсивно:
- Ключи на всех уровнях (top-level, schedule, items[], nested metadata)
- Строковые значения на всех уровнях
- Значения внутри list элементов
- Каждый ключ/значение флажится не более одного раза (break после первого совпадения)

### 2. Payload Compatibility Rules

`validate_payload()` проверяет:
- `adapter_name == "kso"` (обязательно)
- `channel_code == "kso"` (обязательно)
- `dry_run == True` (обязательно)
- `device_code` присутствует и не пуст (обязательно)
- `placement_code` присутствует и не пуст (обязательно)
- `proof_type` — если задан, должен быть из ALLOWED_PROOF_TYPES
- `resolution_width/height` — если заданы, должны быть positive integer
- `duration_seconds` в items — если задан, должен быть positive
- Отсутствие forbidden secret words

### 3. Universal Preview Safety

- `build_payload()` всегда возвращает `dry_run: True`
- `adapter_payload.adapter_name == "kso"`
- В сгенерированном payload нет forbidden keys
- `simulate_delivery()` возвращает `dry_run: True`
- KsoAdapter не импортирует GeneratedManifest
- KsoAdapter не импортирует publication service/generate_manifests/publish_batch
- KsoAdapter не импортирует Device Gateway

### 4. Registry Safety

- `select_adapter("kso")` → KsoAdapter
- `KsoAdapter.supports("kso-pos")` → False
- `KsoAdapter.supports("kso_legacy")` → False
- `select_adapter("nonexistent")` → UnsupportedChannel
- Многократный import adapters модуля не ломает registry
- MockAdapter существует и импортируется, но не в registry (это нормально)

### 5. Legacy Compatibility

KsoAdapter **НЕ** импортирует:
- KsoPlacement
- KsoDevice
- kso_manifest_projection
- publications service (generate_manifests, publish_batch)
- Device Gateway
- GeneratedManifest

### 6. Error/Warning Shape

- `build_payload()` не бросает traceback на пустом/неполном контексте
- `simulate_delivery()` возвращает `ok=False` с errors для invalid payload
- warnings — list[str], всегда сериализуемы
- missing device_code → error в simulate
- missing placement_code → error в simulate

---

## Тесты

**E.2 targeted:** 65 tests (все pass)

| Категория | Тестов |
|---|---|
| FORBIDDEN_SECRET_WORDS coverage | 2 |
| No-secrets top-level | 15 |
| No-secrets nested | 7 |
| No-secrets false positives | 4 |
| Generated payload safety | 2 |
| Payload compatibility | 12 |
| Universal preview safety | 7 |
| Registry safety | 5 |
| Legacy compatibility | 4 |
| Error/warning shape | 4 |
| Compatibility suites | 3 |

---

## Результаты suites

| Suite | Tests | Status |
|---|---|---|
| E.2 targeted | 65 | ✅ 65/65 |
| E.1 targeted | 55 | ✅ 55/55 |
| B.4 orchestrator (b4_1, b4_2, b4_3) | ~110 | ✅ |
| B.5 universal manifest (b5_1, b5_2, b5_3) | ~75 | ✅ |
| C gateway universal manifest | ~48 | ✅ |
| Planning suite | 234 | ✅ 234/234 |
| E.1+E.2+Planning combined | 354 | ✅ 354/354 |
| Backend collection | 1780 | ✅ 0 errors |

---

## Подтверждения

- ✅ **Dry-run only** — adapter всегда возвращает dry_run=True
- ✅ **No GeneratedManifest writes** — 0 импортов/вызовов
- ✅ **Legacy KSO production untouched** — `/kso/{device_code}/manifest` неизменён
- ✅ **kso_manifest_projection untouched** — не импортируется
- ✅ **KsoPlacement/KsoDevice untouched** — не импортируется
- ✅ **Publication flow untouched** — generate_manifests/publish_batch не импортируются
- ✅ **Device Gateway production endpoints untouched**
- ✅ **No DB writes, no migrations, no API changes**
- ✅ **No secrets/signed URLs/tokens in generated payload**

---

## GO/NO-GO для E.3

**GO** ✅ — KSO Adapter прошёл validation gate. Безопасен для universal preview.
E.3 может переходить к KSO Adapter integration test с реальным OrchestratorContext.
