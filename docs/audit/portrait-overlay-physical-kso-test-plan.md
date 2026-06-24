# Portrait Overlay Physical KSO Test Plan — `192.168.110.223`

> **Статус:** 📋 Off-Hours Manual Test Plan (38.0.11)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Безопасный план ручной проверки portrait overlay profile `portrait_idle_overlay_768` на физической test KSO в нерабочее окно.
> **Критически:** Physical overlay render **НЕ одобрен** этим документом — требует отдельного manual approval (см. § Approval Gate).
> **НЕ:** установка runtime, изменение systemd, автозапуск, чтение БД УКМ5, работа с чеками/оплатами/фискальными данными.

---

## 1. Цель теста

| # | Проверка | Критерий |
|---|---|---|
| T1 | Portrait overlay **показывается** в Zone C (y=400-640) при `state=idle` | `smoke result: visible_plan=visible, reason=idle_visible` |
| T2 | Portrait overlay **скрывается** при `kill_switch_active=true` | `smoke result: visible_plan=hidden, reason=kill_switch_hidden` |
| T3 | Portrait overlay **скрывается** при `state=busy/payment/error/offline` | `smoke result: visible_plan=hidden, reason=state_hidden` |
| T4 | Portrait overlay **скрывается** при `state=unknown/stale` | `smoke result: visible_plan=hidden, reason=unknown_hidden/stale_hidden` |
| T5 | **УКМ5 не ломается** — продолжает работать после всех манипуляций | Chromium kiosk active, MintUKM Java process active, кнопка оплаты видна |
| T6 | Kill-switch мгновенно отключает overlay | Создание `/run/verny/kso/kill_switch` → smoke result hidden |
| T7 | Удаление kill-switch + idle state → overlay снова visible | `rm kill_switch` + idle state → smoke result visible |

---

## 2. Preconditions

### 2.1 Обязательные условия

| # | Условие | Проверка |
|---|---|---|
| P1 | **Нерабочее окно** | Магазин закрыт, кассиров нет, продажи не ведутся |
| P2 | **Ответственный сотрудник рядом с КСО** | Физический доступ к экрану, может подтвердить визуально |
| P3 | **SSH доступ подтверждён** | `ssh root@192.168.110.223` работает |
| P4 | **VNC доступ (опционально)** | Для визуального подтверждения без физического присутствия |
| P5 | **Backend НЕ обязателен** | Первый smoke — pure local (только state.json + kill_switch file) |
| P6 | **Rollback plan утверждён** | См. § Rollback Plan — все участники знают команды |
| P7 | **Manual approval от владельца процесса** | Сергей Пащенко (владелец инфраструктуры ivoin.ru) подтверждает окно теста |

### 2.2 Подготовка рабочей директории на КСО

```bash
# Создать (если нет) — требуется root или sudo
mkdir -p /run/verny/kso
chmod 755 /run/verny/kso
```

### 2.3 Проверка текущего состояния КСО

```bash
# УКМ5 работает?
systemctl is-active mint.service        # должно быть: active
systemctl is-active mysql.service       # должно быть: active (или mariadb)
systemctl is-active redis.service       # должно быть: active

# Chromium kiosk работает?
ps aux | grep "[c]hromium"              # должен быть процесс с --kiosk
ps aux | grep "[M]intUKM"               # должен быть java-процесс

# Память (должно быть > 1 GB свободно)
free -h | grep Mem
```

---

## 3. Что запрещено

### 3.1 Категорически запрещено

| # | Действие | Почему |
|---|---|---|
| F1 | **Менять УКМ5** (`mint.service`, `mintukm.jar`, конфиги) | Production кассовая система |
| F2 | **Менять Chromium УКМ5** (аргументы запуска, `--kiosk`, профиль) | Нарушит kiosk-режим |
| F3 | **Менять openbox-autostart / .profile / xinitrc** | Изменит автозапуск УКМ5 |
| F4 | **Создавать или изменять systemd unit для overlay** | Только ручной запуск в этом тесте |
| F5 | **Проводить реальную оплату** | Фискальный риск |
| F6 | **Сканировать реальный товар** | Создаст чек в БД |
| F7 | **Читать БД УКМ5** (MySQL/MariaDB) | Конфиденциальные данные |
| F8 | **Читать логи с чеками/оплатами** | Фискальные/персональные данные |
| F9 | **Использовать реальные товары/чеки/клиентов** | PII + фискальный риск |

### 3.2 Разрешено только в рамках теста

| # | Действие | Ограничение |
|---|---|---|
| A1 | Создать `/run/verny/kso/state.json` | Только synthetic state (`idle`, `unknown`). Без forbidden fields |
| A2 | Создать `/run/verny/kso/kill_switch` | Пустой файл через `touch` |
| A3 | Запустить `python -m kso_player.portrait_smoke` | Только dry smoke без UI (Phase 1). Overlay render — только с отдельным approval (Phase 2) |
| A4 | Удалить временные test files | После завершения теста |

---

## 4. Manual Smoke Phases

### Phase 0 — Readiness Check (5 минут)

**Цель:** подтвердить, что КСО в стабильном состоянии и тестовые файлы можно создать.

```bash
# Step 0.1 — Проверить текущий экран УКМ5
#   Визуально: Chromium kiosk показывает главный экран УКМ5.
#   Через VNC/физически: кнопка оплаты (синяя, y≈720-840) видна.

# Step 0.2 — Проверить /run/verny/kso
ls -la /run/verny/kso/ 2>&1
#   Ожидание: директория существует ИЛИ создаётся (mkdir -p)

# Step 0.3 — Проверить права
touch /run/verny/kso/.write_test && rm /run/verny/kso/.write_test
#   Ожидание: создание/удаление работает без ошибок

# Step 0.4 — Проверить свободную память
free -h | grep Mem
#   Ожидание: available > 1.5 GB

# Step 0.5 — Проверить CPU
top -bn1 | head -5
#   Ожидание: load average < 1.0
```

**Go / No-Go:**
- ✅ Все шаги 0.1-0.5 пройдены → перейти к Phase 1
- ❌ Любой шаг не пройден → **STOP**, зафиксировать проблему, откатить если что-то менялось

---

### Phase 1 — Dry Smoke без UI (10 минут)

**Цель:** проверить полный pipeline `state → observer → kill_switch → shell_plan → visible/hidden` на КСО без запуска графического overlay.

Используется только `python -m kso_player.portrait_smoke` — **NO Chromium launch, NO X11 overlay**.

#### Step 1.1 — Idle → Visible

```bash
# Создать синтетический idle state
cat > /run/verny/kso/state.json << 'STATE_EOF'
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "idle",
  "source": "manual_test",
  "updated_at_utc": "REPLACE_WITH_CURRENT_UTC",
  "stale_after_ms": 999999999
}
STATE_EOF

# Обновить timestamp на текущий
CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sed -i "s/REPLACE_WITH_CURRENT_UTC/$CURRENT_UTC/" /run/verny/kso/state.json

# Запустить smoke
cd /opt/verny/kso  # или путь установки
python3 -m kso_player.portrait_smoke \
    --state-file /run/verny/kso/state.json \
    --kill-switch /run/verny/kso/kill_switch

# ОЖИДАНИЕ:
#   "visible_plan": "visible"
#   "reason": "idle_visible"
#   "state": "idle"
#   "kill_switch_active": false
```

#### Step 1.2 — Kill-Switch → Hidden

```bash
# Создать kill_switch
touch /run/verny/kso/kill_switch

# Запустить smoke с тем же idle state
python3 -m kso_player.portrait_smoke \
    --state-file /run/verny/kso/state.json \
    --kill-switch /run/verny/kso/kill_switch

# ОЖИДАНИЕ:
#   "visible_plan": "hidden"
#   "reason": "kill_switch_hidden"
#   "kill_switch_active": true

# Удалить kill_switch
rm /run/verny/kso/kill_switch
```

#### Step 1.3 — Unknown State → Hidden

```bash
# Создать synthetic unknown state
cat > /run/verny/kso/state.json << 'STATE_EOF'
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "unknown",
  "source": "manual_test",
  "updated_at_utc": "REPLACE_WITH_CURRENT_UTC",
  "stale_after_ms": 999999999
}
STATE_EOF
CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sed -i "s/REPLACE_WITH_CURRENT_UTC/$CURRENT_UTC/" /run/verny/kso/state.json

# Smoke
python3 -m kso_player.portrait_smoke \
    --state-file /run/verny/kso/state.json

# ОЖИДАНИЕ:
#   "visible_plan": "hidden"
#   "reason": "unknown_hidden"
#   "state": "unknown"
```

#### Step 1.4 — Stale Timestamp → Hidden

```bash
# Idle state с ОЧЕНЬ старым timestamp
cat > /run/verny/kso/state.json << 'STATE_EOF'
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "idle",
  "source": "manual_test",
  "updated_at_utc": "2020-01-01T00:00:00Z",
  "stale_after_ms": 5000
}
STATE_EOF

# Smoke
python3 -m kso_player.portrait_smoke \
    --state-file /run/verny/kso/state.json

# ОЖИДАНИЕ:
#   "visible_plan": "hidden"
#   "reason": "stale_hidden"
#   "effective_state": "stale"
```

#### Step 1.5 — Payment State → Hidden

```bash
cat > /run/verny/kso/state.json << 'STATE_EOF'
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "payment",
  "source": "manual_test",
  "updated_at_utc": "REPLACE_WITH_CURRENT_UTC",
  "stale_after_ms": 999999999
}
STATE_EOF
CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sed -i "s/REPLACE_WITH_CURRENT_UTC/$CURRENT_UTC/" /run/verny/kso/state.json

# Smoke
python3 -m kso_player.portrait_smoke \
    --state-file /run/verny/kso/state.json

# ОЖИДАНИЕ:
#   "visible_plan": "hidden"
#   "reason": "state_hidden"
```

#### Step 1.6 — Busy → Hidden, Error → Hidden, Offline → Hidden

```bash
# Повторить для state=busy, state=error, state=offline
for STATE in busy error offline; do
    CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    cat > /run/verny/kso/state.json << STATE_EOF
{
  "schema_version": 1,
  "device_code": "a-05954",
  "state": "$STATE",
  "source": "manual_test",
  "updated_at_utc": "$CURRENT_UTC",
  "stale_after_ms": 999999999
}
STATE_EOF
    echo "=== Testing state=$STATE ==="
    python3 -m kso_player.portrait_smoke \
        --state-file /run/verny/kso/state.json
done

# ОЖИДАНИЕ для каждого: "visible_plan": "hidden", "reason": "state_hidden"
```

**Go / No-Go Phase 1:**
- ✅ Все шаги 1.1-1.6 выдали ожидаемые результаты → перейти к Phase 2 (**только с отдельным approval**)
- ❌ Любой шаг не совпал → **STOP**, зафиксировать расхождение, НЕ переходить к Phase 2

---

### Phase 2 — Overlay Render (ТОЛЬКО с отдельным approval)

> **⚠️ Physical overlay render is NOT approved by this document.**
> **Требуется отдельное ручное разрешение от Сергея Пащенко в момент теста.**

**Preconditions для Phase 2:**
- Phase 1 полностью пройдена (все 6 шагов ✅)
- Владелец процесса дал явное разрешение на render
- Kill-switch `/run/verny/kso/kill_switch` готов к немедленному использованию
- Ответственный сотрудник физически рядом с КСО

**Команда запуска (справочно — НЕ выполнять без approval):**

```bash
# ПРИМЕР КОМАНДЫ — НЕ ВЫПОЛНЯТЬ БЕЗ ЯВНОГО РАЗРЕШЕНИЯ
# Overlay window: x=0 y=400 w=768 h=240, non-fullscreen, no frame, no focus
# Точная команда будет уточнена в момент теста в зависимости от доступных инструментов
# (xdotool, wmctrl, Chromium --app, или другой механизм)
```

**Параметры окна (если render будет выполняться):**

| Параметр | Значение |
|---|---|
| Позиция | x=0, y=400 |
| Размер | 768 × 240 |
| Fullscreen | **false** |
| Kiosk mode | **false** |
| Always on top | **true** (но без перехвата фокуса) |
| No focus steal | **true** |
| Ручной запуск | **да** (не systemd, не autostart) |
| Ручная остановка | **да** (pkill по точному имени процесса) |
| Kill-switch под рукой | **обязательно** |

---

### Phase 3 — Rollback (5 минут)

```bash
# Step 3.1 — Закрыть overlay process (если был запущен в Phase 2)
#   ИСПОЛЬЗОВАТЬ ТОЧНОЕ ИМЯ ПРОЦЕССА — НЕ pkill chromium!
#   pkill -f "kso_player.portrait_smoke"   # если smoke процесс
#   pkill -f "точное_имя_overlay_процесса"  # если отдельный процесс

# Step 3.2 — Создать kill_switch (на всякий случай)
touch /run/verny/kso/kill_switch

# Step 3.3 — Проверить, что УКМ5 работает
systemctl is-active mint.service       # должно быть: active
ps aux | grep "[c]hromium"             # должен быть процесс
ps aux | grep "[M]intUKM"              # должен быть java-процесс

# Step 3.4 — Проверить Chromium УКМ5 визуально
#   Кнопка оплаты видна
#   Header виден
#   Close button виден
#   Экран не чёрный, не белый, не завис

# Step 3.5 — Удалить ТОЛЬКО временные test files
rm -f /run/verny/kso/state.json
rm -f /run/verny/kso/kill_switch
#   НЕ удалять саму директорию /run/verny/kso (может использоваться другими)
#   НЕ удалять другие файлы

# Step 3.6 — Проверить, что НЕ осталось test-процессов
ps aux | grep -E "portrait_smoke|kso_player"
#   Ожидание: пусто (или только grep)

# Step 3.7 — Финальная проверка УКМ5
systemctl is-active mint.service
free -h | grep Mem
#   Ожидание: mint active, память в норме
```

---

## 5. Stop Criteria

**Немедленно прекратить тест при ЛЮБОМ из:**

| # | Ситуация | Действие |
|---|---|---|
| S1 | Overlay **перекрывает** payment button (y=720-840) | `touch /run/verny/kso/kill_switch` → Phase 3 rollback |
| S2 | Overlay **перекрывает** header (y=0-60) или close button (x=725-731, y=4-24) | Kill-switch → rollback |
| S3 | **УКМ5 зависает** (Chromium не реагирует, экран застыл) | Kill-switch → rollback → проверить УКМ5 |
| S4 | **Chromium УКМ5 теряет фокус** (kiosk уходит на задний план) | Kill-switch → rollback → перезапустить Chromium УКМ5 если нужно |
| S5 | **CPU > 90%** или **load average > 4.0** в течение > 10 сек | Kill-switch → rollback |
| S6 | **RAM available < 500 MB** | Kill-switch → rollback |
| S7 | **Появляется ошибка кассы** на экране УКМ5 | Kill-switch → rollback → **НЕ пытаться исправить ошибку кассы** |
| S8 | **VNC/SSH теряется** и не восстанавливается за 30 сек | Физически: выключить/перезагрузить КСО если нужно |
| S9 | **Любой намёк на реальные чековые/платёжные данные** в логах или на экране | Kill-switch → rollback → задокументировать |

---

## 6. Rollback Commands (безопасные, без секретов)

```bash
# ═══════════════════════════════════════════════════════════════
# EMERGENCY ROLLBACK — выполнить при любом stop criteria
# ═══════════════════════════════════════════════════════════════

# 1. Немедленно активировать kill-switch
touch /run/verny/kso/kill_switch

# 2. Остановить ТОЛЬКО test overlay process (если был запущен)
#    ВАЖНО: не pkill chromium — это убьёт УКМ5!
#    ВАЖНО: не systemctl restart mint — это перезагрузит кассу!
pkill -f "kso_player.portrait_smoke" 2>/dev/null || true

# 3. Проверить, что Chromium УКМ5 жив
ps aux | grep "[c]hromium.*kiosk"

# 4. Проверить, что УКМ5 mint.service жив
systemctl is-active mint.service

# 5. НЕ делать:
#    - НЕ pkill chromium (вообще)
#    - НЕ systemctl restart mint
#    - НЕ systemctl restart mysql
#    - НЕ systemctl restart redis
#    - НЕ перезагружать КСО без крайней необходимости

# 6. Удалить временные файлы
rm -f /run/verny/kso/state.json
rm -f /run/verny/kso/kill_switch
```

---

## 7. Approval Gate

> ## ⚠️ Physical overlay render is NOT approved by this document.
>
> Этот документ (Step 38.0.11) одобряет **только Phase 0 (readiness) и Phase 1 (dry smoke без UI)**.
>
> **Phase 2 (overlay render) требует отдельного явного manual approval от Сергея Пащенко в момент теста.**
>
> Без этого approval:
> - Запрещён запуск любого графического окна поверх УКМ5
> - Запрещён запуск Chromium/X11 окна на КСО
> - Запрещены любые изменения видимого интерфейса
>
> Phase 1 (dry smoke) — полностью безопасна: только чтение/создание текстовых файлов
> в `/run/verny/kso/` и запуск `python -m kso_player.portrait_smoke` (чистый вывод в терминал,
> без GUI, без X11, без Chromium).

---

## 8. Технические параметры

### 8.1 Test KSO

| Параметр | Значение |
|---|---|
| IP | 192.168.110.223 |
| OS | Ubuntu 18.04.6 |
| Kernel | 5.4.0-100 |
| CPU | Celeron J1900 (4 cores) |
| RAM | 3.7 GB total, ~2.0 GB free |
| Disk | 110 GB SSD, ~85 GB free |
| Экран | 768 × 1024 portrait |
| Chromium | v114, `--kiosk --window-size=768x1024 -nocursor` |
| WM | Openbox 3.6.1 |
| УКМ5 | MintUKM Java, systemd `mint.service` |

### 8.2 Overlay Profile

| Параметр | Значение |
|---|---|
| Profile code | `portrait_idle_overlay_768` |
| Root screen | 768 × 1024 |
| Overlay zone | x=0, y=400, w=768, h=240 |
| Creative canvas | x=0, y=420, w=768, h=200 (относительно root) |
| Gap to payment | 80 px (y=640 → y=720) |
| Режим | idle-only |
| Hide SLA | < 500 мс |
| Kill-switch path | `/run/verny/kso/kill_switch` |
| State path | `/run/verny/kso/state.json` |

### 8.3 Smoke Harness

| Параметр | Значение |
|---|---|
| Команда | `python3 -m kso_player.portrait_smoke` |
| Pipeline | state.json → state_observer → kill_switch → shell_plan → visible/hidden |
| NO Chromium | ✅ |
| NO X11 | ✅ |
| NO network | ✅ |
| NO UKM5 DB | ✅ |

---

## 9. Файлы

- `docs/audit/portrait-overlay-physical-kso-test-plan.md` — этот документ
- `docs/audit/portrait-player-profile-design.md` — дизайн профиля
- `docs/audit/ukm5-ui-safe-zone-mapping.md` — safe zone mapping
- `docs/audit/kso-portrait-architecture-pivot.md` — архитектурный pivot
- `docs/audit/technical-debt-next-actions.md` — план действий
- `docs/audit/one-kso-pilot-readiness-plan.md` — план test KSO → pilot

---

## Журнал

### 2026-06-24 — Шаг 38.0.11

Создан план ручной проверки portrait overlay на физической test KSO (192.168.110.223):
- Phase 0: Readiness check (5 мин)
- Phase 1: Dry smoke без UI (10 мин, 6 шагов)
- Phase 2: Overlay render — **НЕ одобрен**, требует отдельного manual approval
- Phase 3: Rollback (5 мин, 7 шагов)
- Stop criteria: 9 ситуаций с немедленным прекращением теста
- Approval gate: явное разделение dry smoke (✅) vs overlay render (⛔ requires approval)

Код не менялся. КСО не менялась.

### 2026-06-24 — Шаг 38.1 (Physical KSO Phase 0–1 Execution)

**Phase 0 — Readiness Check:** ✅ **пройден**

- SSH доступ: `ukm5@192.168.110.223` — работает
- УКМ5: Chromium 114 kiosk (768×1024 portrait), MintUKM Java активен
- Ресурсы: RAM 1.9 GB free, CPU load 0.15, диск 85 GB free
- `/run/verny/kso` недоступен на запись пользователю ukm5 (нет root)
- Рабочая директория: `/tmp/kso_test/` (создана, права OK)
- Kill-switch файл: создаётся/удаляется без ошибок

**Phase 1 — Dry Smoke без UI:** ✅ **6/6 пройдено**

Запущено на Python 3.6.9 (штатный python3 на КСО) через standalone smoke-скрипт
`apps/kso_player/scripts/standalone_smoke_py36.py` (самодостаточный, без импортов kso_player):

| # | Кейс | Результат |
|---|------|-----------|
| 1 | Нет state.json | `unknown_hidden` ✅ |
| 2 | idle + нет kill-switch | `idle_visible` ✅ |
| 3 | idle + kill-switch | `kill_switch_active` ✅ |
| 4 | scan (busy) | `state_hidden (scan)` ✅ |
| 5 | idle + stale (2020) | `stale_hidden` ✅ |
| 6 | **idle + микросекунды `.573421Z`** | `idle_visible` ✅ |

**Python 3.6.9 compatibility confirmed:**
- `strptime` с форматом `%Y-%m-%dT%H:%M:%S.%f` корректно обрабатывает микросекунды
- Без `dataclasses`, без `datetime.fromisoformat` (Python 3.7+)
- Весь скрипт — standalone, без зависимостей от `kso_player`

**Phase 2 — Overlay Render:** ⛔ **НЕ запускался, НЕ одобрен**

- Требуется отдельное явное manual approval от Сергея Пащенко
- Chromium overlay НЕ запускался
- УКМ5 НЕ менялась
- X11/window manager НЕ трогались

**Очистка КСО:**
- Временные файлы `/tmp/kso_test/state.json`, `/tmp/kso_test/kill_switch` удалены
- Директория `/tmp/kso_test/` оставлена (может использоваться в будущих тестах)

**Добавлено в репозиторий:**
- `apps/kso_player/scripts/standalone_smoke_py36.py` — standalone smoke-скрипт (Python 3.6+)
- `apps/kso_player/tests/test_state_observer.py` +3 теста: микросекундный timestamp, stale микросекунды, missing state file
- Документы обновлены (все 5 audit docs)

**Regression:** пройдена (см. commit log)

### 2026-06-24 — Шаг 38.1.2 (Phase 2 Overlay Render — Attempted)

**⚠️ VERIFICATION FAILED: visual overlay display is NOT confirmed.**

Phase 2 attempted по разрешению Сергея Пащенко (~44s). Chromium --app PID 25714 запущен, геометрия (0,400) 768×240, без запрещённых flags.

НО:
- `xdotool search --name "Phase 2"` — **окно НЕ найдено**
- `scrot` скриншот не сделан (scrot установлен — упущение)
- Пользователь **не увидел** overlay на экране КСО

Root cause (наиболее вероятно): Openbox stacked --app окно ПОД fullscreen kiosk UKM5.

**Статус:** Phase 2 attempted, **visual display NOT confirmed.**
УКМ5/Chromium/Openbox/systemd не менялись. Временные файлы удалены.

