# Test KSO Phase A — Backend-Only Live Readiness Result

> **Step:** 38.8  
> **Date:** 2026-06-25  
> **Live backend:** ✅ доступен (localhost, dev)  
> **URL:** `<CONFIGURED>` — значение не выводится  
> **Commit:** см. итоговый отчёт

---

## Выполненные HTTP-вызовы

| # | Endpoint | Method | Status |
|---|---|---|---|
| A1 | `/health` | GET | ✅ `{"status":"ok","version":"0.1.0","db":"connected"}` |
| A2 | `/api/test-kso/seed` | POST | ✅ Идемпотентен, `was_already_seeded: true` |
| A3 | `/api/test-kso/readiness?device_code=test-dev-seed` | GET | ✅ Ответ получен |
| A4 | Portal `/readiness` | GET | ✅ 8 секций + Phase D Gate |

---

## Readiness Status (safe summary)

| Поле | Значение | Примечание |
|---|---|---|
| `overall_ready` | **`false`** | ⬅ sidecar config + media cache не готовы |
| `device_registered` | `true` | `test-dev-seed`, active |
| `campaign_registered` | `true` | `test-camp-seed`, active |
| `creative_registered` | `true` | `test-creative-seed`, active, `image/png` |
| `placement_registered` | `true` | `test-place-seed`, active |
| `campaign_creative_linked` | `true` | Link существует |
| `manifest_published` | `true` | `test-manifest-seed`, `published` |
| `manifest_item_count` | `1` | |
| `manifest_has_creative_code` | `true` | |
| `manifest_has_media_ref` | `true` | |
| `publication_exists` | `true` | `published` |
| `sidecar_config_ready` | **`false`** | ⬅ 4 обязательных поля не заполнены |
| `sidecar_config_missing_fields` | `backend_base_url, device_code, device_secret, agent_root` | Имена полей, без значений |
| `media_cache_ready` | **`false`** | ⬅ 1 файл ожидается, не закеширован |
| `media_cache_items_expected` | `1` | |
| `pop_endpoint_ready` | `true` | |
| `phase_d_blocked` | **`true`** | Gate держит |
| `phase_d_block_reason` | `Explicit manual approval required before any physical X11 window` | |

### Remaining Steps

1. Configure sidecar required fields: `backend_base_url`, `device_code`, `device_secret`, `agent_root`
2. Ensure 1 media files cached on KSO
3. Get manual approval for Phase D (controlled physical window)

---

## Исправление контракта readiness

**Проблема:** `overall_ready` возвращал `true`, несмотря на `sidecar_config_ready: false` и `media_cache_ready: false`. Это вводило в заблуждение — backend сообщал «всё готово», когда E2E цепочка была неполной.

**Исправлено:** `overall_ready` теперь требует `sidecar_config_ready=true` **AND** `media_cache_ready=true`.

**Затронутые файлы:**
- `backend/app/domains/test_kso_readiness/service.py` — +2 условия в `all()`
- `backend/tests/test_z_test_kso_readiness_384.py` — 2 теста обновлены (expect `False`)

---

## Live Blockers (после Phase A)

| # | Blocker | Фаза |
|---|---|---|
| 1 | Sidecar config не заполнен на КСО | B |
| 2 | Media cache пуст | C |
| 3 | Phase D manual approval | D |

**Backend технически готов** — все prerequisites (device, campaign, creative, placement, manifest, creativeCode, mediaRef) зелёные. Но overall E2E readiness — `false` до заполнения sidecar config и media cache.

---

## Что НЕ делалось

- ❌ SSH на КСО 192.168.110.223
- ❌ Physical run / X11 / Chromium
- ❌ Настройка sidecar
- ❌ Изменение УКМ5/Openbox/systemd
- ❌ Чтение БД УКМ5 / чеков / фискальных данных
- ❌ Вывод реальных URL / токенов / секретов

---

## Проверка безопасности

- ✅ Backend URL не выведен (`<CONFIGURED>`)
- ✅ Токены/секреты отсутствуют в документе
- ✅ Только имена полей sidecar config, без значений
- ✅ `device_secret` упоминается только как имя поля
