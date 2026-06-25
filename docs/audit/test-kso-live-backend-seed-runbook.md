# Test KSO Live Backend Seed — Operator Preflight Runbook

## 🚨 CRITICAL: This is a READ-ONLY runbook. No physical KSO actions.

> **Статус:** 📋 Phase A–C Preflight (38.7)
> **Дата:** 2026-06-25
> **Цель:** Подготовить оператора к live backend seed перед controlled one-KSO E2E dry run.
> **ВАЖНО:** Никакие действия на физической КСО не выполняются.
> Phase D (физический запуск) заблокирован и требует отдельного manual approval.

---

## Placeholder Conventions

Все реальные значения заменены плейсхолдерами:

| Placeholder | Что заменить | Где взять |
|---|---|---|
| `<TEST_BACKEND_BASE_URL>` | HTTPS URL бэкенда | Оператор знает |
| `<TEST_KSO_DEVICE_CODE>` | Код тестового КСО устройства | Зарегистрирован в бэкенде через portal |
| `<DEVICE_SECRET_VALUE>` | Секрет аутентификации устройства | Генерируется бэкендом при регистрации устройства |
| `<AGENT_ROOT>` | Путь к agent root на КСО | Например `/opt/kso-agent` |

> ⚠️ **НИКОГДА не писать реальные значения этих плейсхолдеров в чат, docs, или git.**
> Реальные значения передаются оператору через защищённый канал (1:1 DM, зашифрованный файл).

---

## Phase A — Backend Readiness (без КСО)

### A1: Проверить backend health

```bash
# На dev-машине (не на КСО):
curl -s http://localhost:8421/health
# Ожидаемый ответ: {"status":"healthy"}
```

Открой portal: `http://localhost:8422/readiness`

### A2: Выполнить synthetic seed

Через portal `/readiness` или напрямую:

```bash
curl -s -X POST http://localhost:8421/api/test-kso/seed \
  -H 'Content-Type: application/json' \
  -d '{"device_code":"test-dev-seed","campaign_code":"test-camp-seed","creative_code":"test-creative-seed","placement_code":"test-place-seed","manifest_code":"test-manifest-seed"}'
```

Ожидаемый ответ:
```json
{
  "overall_success": true,
  "device_seeded": true,
  "campaign_seeded": true,
  "creative_seeded": true,
  "placement_seeded": true,
  "manifest_generated": true,
  "manifest_published": true
}
```

Повторный вызов идемпотентен — вернёт `was_already_seeded: true`.

### A3: Проверить readiness

```bash
curl -s "http://localhost:8421/api/test-kso/readiness?device_code=test-dev-seed"
```

Проверить:
- `overall_ready` должен быть `true`
- `manifest_published` должен быть `true`
- `manifest_has_creative_code` должен быть `true`
- `manifest_has_media_ref` должен быть `true`
- `phase_d_blocked` должен быть `true`

### A4: Убедиться, что Phase D blocked

В ответе readiness:
```json
{
  "phase_d_requires_approval": true,
  "phase_d_blocked": true,
  "phase_d_block_reason": "Explicit manual approval required before any physical X11 window"
}
```

Никаких кнопок «Start», «Deploy», «Run Phase D» на portal `/readiness` нет.

---

## Phase B — Sidecar Config Preparation (на КСО, без backend)

### B1: Заполнить локальный config

Оператор на КСО (192.168.110.223) выполняет:

```bash
# 1. Инициализировать agent root
sidecar init-local-root --root <AGENT_ROOT>

# 2. Записать конфигурацию
sidecar write-config \
  --root <AGENT_ROOT> \
  --backend-base-url <TEST_BACKEND_BASE_URL> \
  --device-code <TEST_KSO_DEVICE_CODE>

# 3. Записать секрет (через stdin — никогда не передавать аргументом!)
echo -n '<DEVICE_SECRET_VALUE>' | sidecar secret-store-set --root <AGENT_ROOT> --stdin
```

### B2: Проверить config без вывода значений

```bash
sidecar config-status --root <AGENT_ROOT>
# Вывод покажет: backend_scheme, backend_host, device_code
# НИКОГДА не покажет device_secret

sidecar secret-store-check --root <AGENT_ROOT>
# Вывод: present=True/False, permissions_ok=True/False
# НИКОГДА не покажет сам secret

sidecar doctor --root <AGENT_ROOT>
# Проверит все папки, config, runtime config, manifest, media cache
```

### B3: Поля, которые НЕЛЬЗЯ писать в чат/docs/git

| Поле | Почему |
|---|---|
| `backend_base_url` | Содержит реальный hostname бэкенда |
| `device_code` | Идентификатор устройства |
| `device_secret` | Секрет аутентификации |
| Любой token/access_token | Креденшелы |

В readiness endpoint эти поля возвращаются **только как имена**, без значений.

---

## Phase C — Dry Preflight (без X11/Chromium)

### C1: Проверить readiness page на portal

Открыть `http://localhost:8422/readiness` (логин: `admin` / `Admin123!`).

Убедиться:
- Все backend prerequisites ✅ (зелёные)
- Sidecar config checklist показывает все 12 полей
- Все required поля помечены ❌ (оператор ещё не заполнил на КСО)
- Phase D gate: ⛔ blocked

### C2: Проверить manifest fetch readiness

```bash
sidecar manifest-status --root <AGENT_ROOT>
```

Если manifest отсутствует — синхронизировать:
```bash
sidecar sync-manifest --root <AGENT_ROOT>
```

После синхронизации проверить:
- `manifest_present: true`
- `items_count >= 1`
- Каждый item содержит `creativeCode` и `mediaRef`

### C3: Проверить media cache readiness

```bash
sidecar doctor --root <AGENT_ROOT>
# Секция "media_cache": cache_items_total, cache_items_cached, cache_missing
```

Ожидается:
- `cache_items_cached == cache_items_total`
- `cache_missing == 0`

### C4: Проверить PoP endpoint readiness

Endpoint `/api/device-gateway/pop/batch` существует в коде бэкенда.
Readiness endpoint всегда возвращает `pop_endpoint_ready: true`.

### C5: Проверить kill-switch и state paths (checklist, без X11)

```bash
# Проверить, что пути существуют как концепт (файлы создадутся при запуске)
sidecar doctor --root <AGENT_ROOT>
# Секции: "config_ok", "agent_status_ok", "folders_ok"
```

Файлы `kill-switch` и `kso_state.json` создаются при первом запуске sidecar.
На этапе preflight достаточно убедиться, что директории agent root существуют.

---

## Что НЕ делать на этом шаге

- ❌ Не запускать `sidecar run-once` (physical run)
- ❌ Не создавать X11 окна
- ❌ Не запускать Chromium
- ❌ Не менять УКМ5/Openbox/systemd
- ❌ Не писать реальные значения секретов в чат/docs/git
- ❌ Не запускать `ssh ukm5@192.168.110.223` без явного разрешения

---

## Readiness Checklist (перед переходом к Phase D)

| # | Шаг | Фаза | Как проверить |
|---|---|---|---|
| 1 | Backend health | A | `curl /health` |
| 2 | Synthetic seed выполнен | A | `POST /api/test-kso/seed` |
| 3 | Manifest published | A | `/api/test-kso/readiness` → `manifest_published: true` |
| 4 | creativeCode + mediaRef в манифесте | A | `/api/test-kso/readiness` → `manifest_has_creative_code: true`, `manifest_has_media_ref: true` |
| 5 | Sidecar config заполнен | B | `sidecar config-status --root <AGENT_ROOT>` |
| 6 | Device secret записан | B | `sidecar secret-store-check --root <AGENT_ROOT>` |
| 7 | Manifest засинхронизирован | C | `sidecar manifest-status --root <AGENT_ROOT>` |
| 8 | Media cache полный | C | `sidecar doctor` → `cache_missing == 0` |
| 9 | Portal /readiness green | C | Открыть portal |
| 10 | Phase D approval | C | ⛔ BLOCKED — требуется manual approval |

---

## После выполнения Phase A–C

Оператор докладывает:
- Все 9 шагов readiness checklist выполнены
- Sidecar config заполнен (имена полей ✅, значения ❌ не переданы)
- Phase D всё ещё blocked

Следующий шаг: **38.9 — Phase B Sidecar Config Preparation** (подготовка config template, валидация плейсхолдеров, без физической КСО).

See also: `docs/audit/test-kso-sidecar-config-preparation.md`
