# Test KSO End-to-End Readiness Gate

> **Статус:** 📋 Technical Validation Gate (37.12)
>
> Дата: 2026-06-16
> Ревизия: 1
>
> **Назначение:** Проверить полную цепочку на одном test KSO перед pilot rollout на группу КСО.
> **НЕ:** пилотный запуск, production, multi-store rollout.

---

## Что уже готово (37.x technical validation)

| # | Компонент | Статус | Где проверено |
|---|---|---|---|
| 1 | Backend /health | ✅ | `curl http://127.0.0.1:8001/health` → 200 |
| 2 | Portal login + session | ✅ | /login работает, RBAC enforced |
| 3 | Hierarchy (1 branch + 1 cluster + 1 store + 1 KSO) | ✅ | Синтетический seed: `demo_branch_north` / `demo_cluster_001` / `demo_store_001` / `demo_kso_001` |
| 4 | Creative upload 1440×1080 через portal | ✅ | `/creatives` upload form + validation |
| 5 | Campaign create (test KSO) | ✅ | `/campaigns` → backend `POST /api/campaigns/test-kso` |
| 6 | Placement / schedule (test KSO) | ✅ | `/schedule` → backend `POST /api/schedule/test-kso` |
| 7 | Approval request + decide (test KSO) | ✅ | `/approvals` → backend maker-checker |
| 8 | Manifest generation (test KSO) | ✅ | `/publications` → backend `POST /api/manifests/test-kso/generate` |
| 9 | Manifest publish (test KSO) | ✅ | `/publications` → backend `POST /api/manifests/test-kso/{code}/publish` |
| 10 | Device manifest endpoint | ✅ | `GET /api/device-gateway/kso/{device_code}/manifest` (TEST_ONLY) |
| 11 | Sidecar fetch contract | ✅ | 1838 тестов — extractor совместим с published manifest wrapper |
| 12 | Player local smoke | ✅ | 968 тестов — render plan + shell snapshot без реального Chromium |
| 13 | PoP ingest | ✅ | `POST /api/device-gateway/kso/{device_code}/pop` (TEST_ONLY, 164 backend тестов) |
| 14 | Portal PoP view | ✅ | `/proof-of-play` — backend-driven, KPI + фильтры + safe table |
| 15 | KSO Linux infra package | ✅ | systemd templates × 3, bootstrap (dry-run), preflight, release builder |
| 16 | State adapter | ✅ | 86 тестов — file source daemon, UKM4 safe state |

**Техническая цепочка замкнута на уровне unit/integration тестов:**
```
creative → campaign → placement → approval → manifest → publish → device gateway → sidecar smoke → player smoke → PoP ingest → portal PoP view
```

**Regression baseline:** ~3700 тестов, все green.

---

## Что нужно подготовить перед установкой на test KSO

### 1. Параметры test KSO

| Параметр | Значение |
|---|---|
| Оборудование | ServPlus Sherman-J 5.1 или эквивалент |
| ОС | Linux (systemd) |
| Экран | 1920×1080 |
| Ad zone | 1440×1080 |
| Браузер | Chromium (kiosk-mode) |
| Кассовая система | СуперМаг УКМ 4 |
| Состояние КСО | UKM4 safe state через State Adapter |
| Сеть | Доступ к backend API |

### 2. Конфигурационные файлы на test KSO

Конфиги размещаются в `/etc/verny/kso/`.

**`sidecar.env`** (chmod 600):
```ini
# Backend URL (внутренняя сеть)
VERNY_KSO_BACKEND_URL=<backend_base_url>

# Идентификатор устройства (из backend device registry)
VERNY_KSO_DEVICE_CODE=<device_code>

# Device secret (из backend device credential — хранить безопасно, НЕ в git)
VERNY_KSO_DEVICE_SECRET=<device_secret>

# Режим: test KSO technical validation
VERNY_KSO_MODE=test_kso
```

**`player.env`**:
```ini
# Режим: только синтетический тест, без реального Chromium kiosk
VERNY_KSO_PLAYER_MODE=test_kso

# Shell snapshot output (read-only проверка render plan)
VERNY_KSO_PLAYER_SHELL_SNAPSHOT=/var/lib/verny/kso/runtime/shell_snapshot.html
```

**`state-adapter.env`**:
```ini
# Источник UKM4 safe state
VERNY_KSO_STATE_SOURCE=static

# Статическое состояние (тестовое)
VERNY_KSO_STATIC_STATE=test_kso_active
```

### 3. Локальные workspace paths на test KSO

| Путь | Назначение | Права |
|---|---|---|
| `/opt/verny/kso/` | Исходники приложения | read-only |
| `/etc/verny/kso/` | Конфигурация | read-only (secret: 600) |
| `/var/lib/verny/kso/state/` | UKM4 state adapter output | read-write |
| `/var/lib/verny/kso/manifest/` | Локальный manifest | read-write |
| `/var/lib/verny/kso/media/` | Локальный media cache | read-write |
| `/var/lib/verny/kso/pop/pending/` | PoP pending (player пишет) | read-write |
| `/var/lib/verny/kso/pop/sent/` | PoP sent (sidecar перемещает) | read-write |
| `/var/lib/verny/kso/runtime/` | Runtime shell (мутабельная копия) | read-write |
| `/run/verny/kso/` | Runtime health (tmpfs) | read-write |
| `/var/log/verny/kso/` | Логи | read-write |

### 4. Имена сервисов (systemd)

| Сервис | Описание |
|---|---|
| `kso-state-adapter` | UKM4 state → файловый источник |
| `kso-sidecar` | Синхронизация manifest/media, отправка PoP |
| `kso-player` | Локальный цикл показа + PoP writer |

---

## Пошаговая E2E проверка

### Шаг 1 — Загрузить synthetic creative 1440×1080

1. Войти в портал (admin / пароль)
2. Перейти на `/creatives`
3. Создать synthetic PNG 1440×1080 (чёрный фон + белый текст «TEST KSO»)
4. Заполнить форму: `creative_code` = `test_kso_creative_001`, имя = «Test KSO Creative 001»
5. Загрузить файл
6. **Проверка:** креатив появился в таблице со статусом `active`

### Шаг 2 — Создать campaign

1. Перейти на `/campaigns`
2. `campaign_code` = `test_kso_campaign_001`
3. Имя = «Test KSO Campaign 001»
4. Привязать `test_kso_creative_001`
5. **Проверка:** кампания создана, статус `draft`

### Шаг 3 — Создать placement на test KSO

1. Перейти на `/schedule`
2. `device_code` = `demo_kso_001` (из seed)
3. `campaign_code` = `test_kso_campaign_001`
4. `creative_code` = `test_kso_creative_001`
5. Даты: сегодня → сегодня + 7 дней
6. **Проверка:** placement создан, `status` = `draft`

### Шаг 4 — Запросить approval

1. Перейти на `/approvals`
2. `target_type` = `placement`
3. `target_code` = код placement из шага 3
4. **Проверка:** approval request создан, `status` = `pending_approval`

### Шаг 5 — Approve

1. На `/approvals` нажать «Решить» на созданном запросе
2. Решение: `approved`
3. **Проверка:** `status` = `approved`, campaign/placement перешли в `approved`

### Шаг 6 — Generate manifest

1. Перейти на `/publications`
2. `placement_code` = код из шага 3
3. Нажать «Сгенерировать Manifest»
4. **Проверка:** manifest создан, `status` = `generated`

### Шаг 7 — Publish manifest

1. На `/publications` нажать «Опубликовать» на сгенерированном manifest
2. **Проверка:** `status` = `published`

### Шаг 8 — Sidecar fetch (smoke на test KSO)

1. На test KSO: запустить sidecar в dry-run режиме
2. Проверить, что `GET /api/device-gateway/kso/{device_code}/manifest` возвращает published manifest
3. **Проверка:** sidecar extractor успешно читает wrapper, извлекает safe поля

### Шаг 9 — Player local render/smoke

1. На test KSO: запустить player в smoke-режиме (без Chromium)
2. Проверить shell snapshot — render plan валиден
3. **Проверка:** player генерирует корректный playlist из manifest

### Шаг 10 — Отправить PoP

1. На test KSO: player записывает PoP event → `pop/pending/`
2. Sidecar забирает event → отправляет на `POST /api/device-gateway/kso/{device_code}/pop`
3. **Проверка:** backend возвращает `{"status": "accepted", ...}`

### Шаг 11 — Увидеть PoP в portal

1. Войти в портал
2. Перейти на `/proof-of-play`
3. Установить фильтр по `device_code` = `demo_kso_001`
4. **Проверка:** таблица показывает PoP события, KPI обновлены

---

## Критерии успеха test KSO проверки

| # | Критерий | Статус |
|---|---|---|
| ✅ | Все 11 шагов E2E цепочки выполнены без ошибок | Ожидает |
| ✅ | Manifest сгенерирован и опубликован через портал | Ожидает |
| ✅ | Sidecar получает manifest через device gateway endpoint | Ожидает |
| ✅ | Player генерирует валидный render plan | Ожидает |
| ✅ | PoP событие принято backend и видно в портале | Ожидает |
| ✅ | Никакие forbidden fields не просочились в ответы/portal | Ожидает |
| ✅ | Все regression suites green после проверки | Ожидает |

---

## Stop Criteria — когда тест надо остановить

| # | Ситуация | Действие |
|---|---|---|
| 🛑 | Backend `/health` возвращает не 200 | Остановить тест, проверить backend логи |
| 🛑 | Portal недоступен или 5xx | Остановить тест, проверить portal логи |
| 🛑 | Device manifest endpoint возвращает 5xx | Остановить тест, проверить manifest generation |
| 🛑 | Sidecar не может подключиться к backend | Проверить сеть, backend URL, device credential |
| 🛑 | Player shell snapshot содержит ошибки | Проверить manifest body, creative refs |
| 🛑 | PoP ingest возвращает 4xx/5xx | Проверить correlation chain, manifest status |
| 🛑 | Portal PoP view пуст при наличии событий | Проверить permission `reports.read`, фильтры |
| 🛑 | Любой regression suite ломается | Остановить, найти причину, исправить до продолжения |

---

## Rollback на test KSO

1. **Остановить сервисы:**
   ```bash
   systemctl stop kso-player kso-sidecar kso-state-adapter
   ```
2. **Сбросить состояние:**
   ```bash
   echo "VERNY_KSO_STATIC_STATE=unknown" > /etc/verny/kso/state-adapter.env
   ```
3. **Очистить runtime:**
   ```bash
   rm -rf /var/lib/verny/kso/manifest/*
   rm -rf /var/lib/verny/kso/media/*
   rm -rf /var/lib/verny/kso/pop/pending/*
   rm -rf /var/lib/verny/kso/pop/sent/*
   rm -rf /var/lib/verny/kso/runtime/*
   rm -rf /run/verny/kso/*
   ```
4. **Восстановить предыдущую версию (если была):** из backup `/opt/verny/kso.backup/`
5. **Проверить backend:** `curl http://<backend>/health`
6. **Решение:** продолжать отладку или откатить полностью

---

## Что НЕ считается готовым для pilot rollout

| # | Компонент | Почему не готов |
|---|---|---|
| ❌ | Реальный Chromium kiosk | Только shell snapshot; нужен графический launch + проверка рендеринга |
| ❌ | Реальный UKM4 state | Только static fallback; нужен реальный source adapter |
| ❌ | Production auth на device gateway | TEST_ONLY — без аутентификации; нужен device auth / mTLS |
| ❌ | Media синхронизация через MinIO | Только local workspace; нужна реальная доставка media |
| ❌ | Множество КСО / магазинов | Только 1 КСО; нужна scale-проверка |
| ❌ | Excel / BI отчётность | Portal PoP view есть, но без Excel/BI |
| ❌ | Real hardware longevity | Не тестировалась стабильность ≥ 24ч на реальном железе |
| ❌ | Network resilience | Не тестировались сценарии временной потери сети |

---

## Что надо сделать после успешной test KSO проверки для pilot rollout

| # | Этап | Описание |
|---|---|---|
| 1 | **Real Chromium kiosk** | Заменить shell snapshot на реальный Chromium launch с `--kiosk` |
| 2 | **Real UKM4 integration** | Подключить реальный state adapter к UKM4 |
| 3 | **Production device auth** | Заменить TEST_ONLY эндпоинты на аутентифицированные с mTLS |
| 4 | **Media delivery** | Настроить MinIO/media синхронизацию от backend до КСО |
| 5 | **Scale check** | Протестировать 3–5 КСО в 2–3 магазинах |
| 6 | **Stability run** | 24–72 часа непрерывной работы на реальном железе |
| 7 | **Excel export** | Добавить выгрузку отчётов (RLS-aware) |
| 8 | **Runbook update** | Обновить документацию по результатам реального запуска |
| 9 | **Rollout decision** | Принять решение о пилотном запуске на группе КСО |

---

## Файлы

- `docs/audit/test-kso-end-to-end-readiness-gate.md` — этот документ
- `docs/audit/one-kso-pilot-readiness-plan.md` — план test KSO → pilot rollout
- `infra/kso-linux/README.md` — KSO Linux deployment
- `infra/kso-linux/install/kso_linux_bootstrap.py` — safe bootstrap (dry-run)
- `infra/kso-linux/preflight/kso_linux_preflight.py` — preflight validator
- `infra/kso-linux/env-examples/` — примеры конфигов
- `infra/kso-linux/systemd/` — systemd unit templates

## Обновления

### Шаг 37.12 — Test KSO End-to-End Readiness Gate (2026-06-16)

Создан документ. Код не менялся. Regression baseline подтверждён.
Уточнено различие: **test KSO technical validation** (1 КСО) vs **pilot rollout** (группа КСО/магазинов).
