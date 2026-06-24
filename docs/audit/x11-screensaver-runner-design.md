# X11 Screensaver Runner Design — `x11_screensaver_runner`

> **Статус:** 📐 Design + Contract (38.1.9)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Создать безопасный state-driven runtime runner для fullscreen idle screensaver на базе X11 click-through renderer.
> **НЕ:** физический запуск на КСО, создание X11 окон, изменение КСО.
>
> **Предыдущий шаг:** 38.1.8 — Physical X11 Click-through Proof успешно выполнен. B-FS-1/B-FS-2 закрыты.
> **Следующий шаг:** 38.1.10 — Guarded physical screensaver run на КСО (отдельный шаг с explicit approval).

---

## 1. Purpose

X11 Screensaver Runner — это управляемый рантайм для fullscreen idle screensaver. Он обеспечивает:

- **State-driven visibility**: показывает заставку только когда КСО в idle и kill-switch неактивен
- **Быстрое скрытие**: по изменению состояния, kill-switch, ошибке (SLA ≤ 500ms)
- **Безопасность**: не запускает Chromium, не трогает УКМ5 DB, не логирует чувствительные данные
- **Guarded execution**: run_once требует explicit approval token

---

## 2. Lifecycle

```
build_plan → validate_plan → acquire_lockfile → check_kill_switch →
read_safe_state_snapshot → decide_visibility → show_if_allowed →
periodic_state_check → hide_on_unsafe_state → timeout →
targeted_rollback → release_lockfile → safe_summary_output
```

### 2.1 Фазы

| # | Фаза | Описание | X11? |
|---|---|---|---|
| 1 | **build_plan** | Создать ScreensaverRunPlan из CLI аргументов | Нет |
| 2 | **validate_plan** | Проверить безопасность плана, запрещённые команды | Нет |
| 3 | **acquire_lockfile** | Захватить `/run/verny/kso/x11_screensaver.lock` | Нет |
| 4 | **check_kill_switch** | Проверить `/run/verny/kso/kill_switch` | Нет |
| 5 | **read_safe_state_snapshot** | Прочитать state.json через state_observer | Нет |
| 6 | **decide_visibility** | Решить: показывать или скрывать | Нет |
| 7 | **show_if_allowed** | Создать X11 окно через renderer contract | Да |
| 8 | **periodic_state_check** | Периодически перечитывать state.json | Нет |
| 9 | **hide_on_unsafe_state** | Скрыть окно при не-idle/ks/forbidden | Да |
| 10 | **timeout** | Остановка по max_duration_sec | Нет |
| 11 | **targeted_rollback** | Убрать своё окно, удалить lockfile | Да |
| 12 | **release_lockfile** | Освободить lockfile | Нет |
| 13 | **safe_summary_output** | Вывести ScreensaverRunResult | Нет |

---

## 3. State-Driven Rules

### 3.1 Visibility Decision

```
kill_switch_active → HIDDEN (kill_switch)
state = idle      → VISIBLE (idle_ks_inactive)
state ≠ idle      → HIDDEN (hidden_state)
state = stale     → HIDDEN (hidden_stale)
state = unknown   → HIDDEN (hidden_missing_state)
forbidden fields  → HIDDEN (hidden_forbidden)
```

### 3.2 Hide Rules (from interaction_hide)

Все правила из `interaction_hide.should_hide()` применяются:
- kill_switch → hide immediately (200ms)
- state_change → hide (500ms)
- keydown/input → hide (200ms)
- touch/pointer → hide (200ms)
- click/wheel → hide (200-300ms)

### 3.3 Forbidden States

Следующие состояния ВСЕГДА приводят к скрытию:
- `busy`, `scan`, `cart`, `payment`, `error`
- `offline`, `unknown`, `stale`
- Любое состояние с forbidden fields в state.json

---

## 4. Safety Controls

### 4.1 Execution limits

| Параметр | Значение | Hard max |
|---|---|---|
| max_duration_sec | 30 (default) | 60 |
| poll_interval_sec | 0.5 | — |

### 4.2 Forbidden Operations

Runner НИКОГДА не выполняет:

| Категория | Запрещено |
|---|---|
| **Process control** | `pkill chromium`, `killall chromium` |
| **Systemd** | `systemctl restart/stop/enable/disable` mint, mysql, redis, chromium |
| **System** | `reboot`, `shutdown`, `poweroff`, `halt` |
| **Autostart** | `systemctl enable`, `crontab -e`, `.profile`, `.xinitrc` |
| **UKM5 files** | openbox, .profile, xinitrc, index.html, autostart |
| **UKM5 DB** | MySQL, Redis, camera_agent — НИКАКОГО доступа |
| **Secrets** | backend URL, tokens, passwords, device_secret |
| **Receipt/PII** | receipt_id, payment, fiscal, customer, card, pan, email |

### 4.3 Rollback

- Rollback targeted ONLY: своё окно + свой lockfile
- НЕ трогает другие процессы
- НЕ рестартит mint/mysql/redis/Chromium
- НЕ меняет permanent config

### 4.4 Output Safety

ScreensaverRunResult содержит ТОЛЬКО safe поля:
- runner name, version, mode
- started, visible, reason, state
- kill_switch_active, duration_sec
- rollback_done, stop_reason, proof_summary
- renderer_plan_valid, renderer_production_ready

НИКОГДА не содержит:
- receipt/payment/fiscal/customer/card/PII
- scanner values, barcodes, key events
- backend URL, tokens, secrets, passwords
- device_secret, api_key

---

## 5. CLI Modes

| Mode | Описание | X11? | Approval? |
|---|---|---|---|
| `--dry-run` | Собрать план, провалидировать, симулировать lifecycle | Нет | Нет |
| `--preflight-only` | Проверить окружение, прочитать state, readiness | Нет | Нет |
| `--run-once` | Выполнить screensaver run | Да (в 38.1.10+) | **Да** (token) |

### 5.1 CLI Args

```
--dry-run | --preflight-only | --run-once
--display            X11 display (default: ':0')
--duration           Max runtime seconds (max 60, default: 30)
--state-file         Path to state JSON
--kill-switch        Path to kill-switch flag
--approval-token     Required for --run-once (USER_APPROVED_RUN_ONCE)
```

---

## 6. Integration Points

| Компонент | Зачем |
|---|---|
| `state_observer` | Чтение `state.json` → PlayerStateSnapshot |
| `kill_switch` | Проверка `/run/verny/kso/kill_switch` |
| `interaction_hide` | Правила скрытия (should_hide) |
| `x11_click_through_renderer` | Контракт окна (geometry, pass-through) |

---

## 7. Blocker Status (after 38.1.8)

| ID | Статус | Примечание |
|---|---|---|
| B-FS-1 | 🟢 Закрыт (X11/focus) | X11 click-through proof: active window = УКМ5 |
| B-FS-2 | 🟢 Закрыт (renderer) | Отдельный X11 renderer без Chromium |
| B-FS-3 | 🟡 Guarded runner | Требует runner validation + HW scanner E2E + pilot |

---

## 8. Physical Run Plan (шаг 38.1.10+, НЕ сейчас)

38.1.9 — только контракт и тесты. Физический run на КСО:

1. Pre-flight (SSH, DISPLAY, state.json, kill_switch)
2. Dry-run симуляция на КСО
3. `--run-once --approval-token USER_APPROVED_RUN_ONCE`
4. X11 окно 768×1024, override-redirect, XFixes input empty
5. Периодическая проверка state (poll interval 0.5s)
6. Скрытие по kill_switch/state/forbidden
7. Timeout (max 30s test, 60s hard max)
8. Rollback: unmap → destroy → close display
9. Cleanup: lockfile, tmp files
10. Safe summary output (no secrets/PII/scanner values)

---

## 9. Journal

| Дата | Событие |
|---|---|
| 2026-06-24 | 38.1.9 — Runner design + contract + 0 тестов |
