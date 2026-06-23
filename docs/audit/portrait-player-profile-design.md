# Portrait Player Profile Design — `portrait_idle_overlay_768`

> **Статус:** 📐 Architecture Design (38.0.5)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Спроектировать новый v1 player profile для реальных КСО сети: 768×1024 portrait, УКМ5 fullscreen kiosk, показ рекламы только в безопасной idle-зоне.
> **НЕ:** реализация, изменение кода, установка на КСО.

---

## 1. Profile Identity

| Параметр | Значение |
|---|---|
| **Profile name** | `portrait_idle_overlay_768` |
| **Profile code** | `portrait_idle_overlay_768` (используется в manifest, конфигах, тестах) |
| **Target fleet** | Все КСО сети: 768×1024 portrait, УКМ5 fullscreen Chromium kiosk |
| **DS dependency** | Нет — независимый player profile |
| **Старый landscape** | Снят как v1 target. Сохранён как `landscape_split_1920` для будущих КСО |

### Design philosophy

> Player — это **гость** на экране УКМ5. Он не владеет экраном, не конкурирует за фокус, не меняет кассовый интерфейс. Он показывает контент только когда это безопасно, и мгновенно исчезает при любой активности.

---

## 2. Геометрия

### 2.1 Root screen

```
┌──────────────────────────────────────┐ y=0
│                                      │
│         768 × 1024 portrait          │
│         (root screen :0)             │
│                                      │
│         УКМ5 Chromium kiosk          │
│         (fullscreen, 0,0)            │
│                                      │
│  ┌────────────────────────────────┐  │ y=400
│  │  OVERLAY ZONE (player)         │  │
│  │  768 × 240                     │  │
│  │  ┌──────────────────────────┐  │  │
│  │  │  CREATIVE CANVAS         │  │  │
│  │  │  768 × 200, centered     │  │  │
│  │  │                          │  │  │
│  │  └──────────────────────────┘  │  │
│  └────────────────────────────────┘  │ y=640
│                                      │
│  ┌────────────────────────────────┐  │
│  │  BLUE PAYMENT BUTTON           │  │ y=720
│  │  (92×120, center x=532)        │  │
│  │  ❌ NEVER OVERLAY              │  │
│  └────────────────────────────────┘  │ y=840
│                                      │
└──────────────────────────────────────┘ y=1024
```

### 2.2 Точные координаты

| Элемент | x | y | w | h | Примечание |
|---|---|---|---|---|---|
| Root screen | 0 | 0 | 768 | 1024 | Портрет |
| Overlay safe zone | 0 | 400 | 768 | 240 | Idle-only зона показа |
| Creative canvas | 0 | 420 | 768 | 200 | Центрировано внутри overlay zone |
| Top margin | — | 400 | — | 20 | Отступ от yellow separator |
| Bottom margin | — | 620 | — | 20 | Gap до payment button (y=720) |
| Gap to payment btn | — | 640 | — | 80 | Безопасный зазор |
| **Payment button** | 487 | 720 | 92 | 120 | ❌ Категорически не перекрывать |

### 2.3 Safe margins

```
Overlay zone:    y=400..640  (240 px)
  Top margin:    y=400..420  ( 20 px) — breathing room от separator
  Canvas:        y=420..620  (200 px) — creative rendering area
  Bottom margin: y=620..640  ( 20 px) — breathing room до payment zone
  Gap:           y=640..720  ( 80 px) — безопасный зазор до кнопки ОПЛАТА
Payment zone:    y=720..840  (120 px) — ❌ NEVER OVERLAY
```

---

## 3. Режимы (States)

### 3.1 Состояния player

| State | Ad показывается | Поведение |
|---|---|---|
| `idle` | ✅ Да | Показывать creative loop. Писать PoP за каждый фактически показанный кадр |
| `busy` | ❌ Нет | Мгновенно скрыть overlay (< 500 мс). Не писать PoP |
| `payment` | ❌ Нет | Мгновенно скрыть. Кнопка оплаты всегда видима. **Enforced на уровне геометрии** |
| `scan` | ❌ Нет | Кассир сканирует товар. Скрыть, не мешать |
| `cart` | ❌ Нет | Корзина открыта. Скрыть |
| `error` | ❌ Нет | Ошибка на экране УКМ5. Скрыть |
| `unknown` | ❌ Нет | Безопасный default — всегда скрыто |
| `stale` | ❌ Нет | Нет свежего сигнала > TTL. Скрыть |
| `offline` | ⚠️ Conditional | Только с локально закешированным контентом. Иначе скрыть |

### 3.2 Переходы

```
                    ┌─────────────────────┐
    start ────────→ │       IDLE          │
                    │   (show creative)   │
                    └──────┬──────────────┘
                           │ state → busy/scan/cart/payment/error/stale/unknown
                           ▼
                    ┌─────────────────────┐
                    │      HIDDEN         │
                    │  (overlay unmapped) │
                    └──────┬──────────────┘
                           │ state → idle (после N секунд бездействия)
                           ▼
                    ┌─────────────────────┐
                    │       IDLE          │
                    └─────────────────────┘
```

### 3.3 Hide SLA

| Триггер | Макс. время скрытия | Метод |
|---|---|---|
| `state` → busy/payment/error | < 500 мс | `xdotool windowunmap` или эквивалент |
| Kill-switch (file flag) | < 500 мс | Проверка на каждом cycle tick |
| Kill-switch (backend command) | < 5 сек | Sidecar polling |
| Kill-switch (systemctl stop) | < 2 сек | SIGTERM → cleanup → exit |

---

## 4. State Contract

### 4.1 Минимальный контракт (JSON)

```json
{
  "schema_version": 1,
  "device_code": "demo_kso_001",
  "state": "idle",
  "source": "ukm5_safe_observer",
  "updated_at_utc": "2026-06-24T00:00:00Z"
}
```

### 4.2 Поля контракта

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `schema_version` | int | ✅ | Версия схемы (1) |
| `device_code` | string | ✅ | Идентификатор КСО (из backend device registry) |
| `state` | string | ✅ | Текущее состояние: `idle`, `busy`, `payment`, `error`, `offline`, `unknown`, `stale` |
| `source` | string | ✅ | Источник состояния: `ukm5_safe_observer` |
| `updated_at_utc` | ISO8601 | ✅ | Время последнего обновления состояния |

### 4.3 Разрешённые значения `state`

| Значение | Семантика | Ad показывается |
|---|---|---|
| `idle` | Экран неактивен > N секунд. Нет касаний, нет продажи | ✅ |
| `busy` | Активная продажа: выбор товаров, навигация | ❌ |
| `payment` | Идёт оплата | ❌ |
| `scan` | Сканирование товара | ❌ |
| `cart` | Корзина открыта | ❌ |
| `error` | Ошибка на экране УКМ5 | ❌ |
| `offline` | Нет сети до backend | ⚠️ local cache only |
| `unknown` | Сигнал не получен / инициализация | ❌ |
| `stale` | Последний сигнал старше TTL | ❌ |

### 4.4 Категорически запрещено в state contract

| Запрещённое поле | Причина |
|---|---|
| `receipt_id` | Фискальные данные |
| `transaction_id` | Идентификатор транзакции |
| `payment_amount` | Сумма оплаты |
| `payment_method` | Способ оплаты |
| `fiscal_data` | Фискальные данные (любые) |
| `customer_name` | Персональные данные |
| `customer_phone` | Телефон |
| `customer_email` | Email |
| `card_number` / `pan` | Номер карты |
| `items[]` | Товарные строки чека |
| `total_amount` | Сумма чека |
| `cashier_id` / `cashier_name` | Идентификация кассира |

---

## 5. Player Behavior

### 5.1 Что player делает

| # | Действие | Описание |
|---|---|---|
| 1 | Читает state contract | Из local файла (пишется state adapter'ом) |
| 2 | Читает local manifest | Из `/var/lib/verny/kso/manifest/current.json` (доставляется sidecar'ом) |
| 3 | Читает local media cache | Из `/var/lib/verny/kso/media/` |
| 4 | Показывает creative loop | Только в состоянии `idle` на overlay zone y=400-640 |
| 5 | Пишет PoP | За каждый фактически показанный кадр в `/var/lib/verny/kso/pop/pending/` |
| 6 | Скрывается мгновенно | При `state` ≠ `idle` — unmaps overlay window |
| 7 | Проверяет kill-switch | На каждом cycle tick |
| 8 | Работает offline | С закешированным контентом (если есть) или скрывается |

### 5.2 Что player НЕ делает

| # | Запрет | Причина |
|---|---|---|
| 1 | Не fullscreen | Окно только в overlay zone (768×240) |
| 2 | Не перезапускает УКМ5 | Кассовая система не затрагивается |
| 3 | Не меняет HTML УКМ5 | `~/mint/bin/www/index.html` не трогается |
| 4 | Не меняет openbox-autostart | Автозапуск не модифицируется |
| 5 | Не читает БД УКМ5 | MySQL (port 3306) не query'тся |
| 6 | Не читает чеки/платежи/фискальные данные | Категорический запрет |
| 7 | Не перекрывает payment button | Геометрически enforced: overlay zone y=400-640, payment button y=720-840 |
| 8 | Не перекрывает header/close | Геометрически enforced: overlay zone начинается с y=400 |
| 9 | Не захватывает фокус | Overlay window без фокуса |
| 10 | Не запускает второй Chromium | Использует X11 overlay, не отдельный браузер |

### 5.3 Overlay window properties

| Параметр | Значение |
|---|---|
| Window type | X11 override-redirect (без управления WM) |
| Фокус | Never takes focus |
| Input | Transparent to input (passthrough) |
| Z-order | Above UKM5 Chromium, below any system dialogs |
| Decorations | None (borderless) |
| Background | Transparent (где нет creative) |

---

## 6. Delivery Model

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────┐
│ Backend  │────→│ Sidecar  │────→│ Local Cache   │────→│ Player   │
│ (remote) │     │ (daemon) │     │ /var/lib/...  │     │ (overlay)│
└──────────┘     └──────────┘     └──────────────┘     └──────────┘
                       │                                      │
                       │ PoP pickup                           │ PoP write
                       ▼                                      ▼
                ┌──────────┐                          ┌──────────────┐
                │ Backend  │←─────────────────────────│ PoP pending  │
                │ PoP API  │                          │ /pop/pending │
                └──────────┘                          └──────────────┘
```

### Offline behaviour

| Сценарий | Поведение |
|---|---|
| Backend недоступен | Sidecar не может получить новый manifest. Player показывает последний закешированный |
| Sidecar недоступен | Player показывает закешированный manifest. PoP копится локально |
| Player запущен, кеша нет | Player в состоянии HIDDEN. Ждёт первый manifest |
| State adapter недоступен | State = `stale` → player скрыт |
| Всё недоступно | Player скрыт. Никакого показа. Безопасный default |

---

## 7. Kill-Switch Design

### Уровень 1: Local file flag

| Параметр | Значение |
|---|---|
| **Механизм** | Player проверяет наличие файла `/run/verny/kso/kill_switch` каждый cycle tick |
| **Срабатывание** | Если файл существует → мгновенное скрытие + graceful shutdown |
| **Кто устанавливает** | State adapter, operator, watchdog |
| **Время реакции** | < 500 мс (на следующем cycle tick) |
| **Создание** | `touch /run/verny/kso/kill_switch` |
| **Сброс** | `rm /run/verny/kso/kill_switch` + restart player |

### Уровень 2: Backend command flag

| Параметр | Значение |
|---|---|
| **Механизм** | Backend выставляет `kill_switch: true` в manifest/device command |
| **Доставка** | Sidecar при следующем pull (≤ 30 сек) записывает локальный файл |
| **Время реакции** | < 35 сек (sidecar polling cycle + player tick) |
| **Применение** | Удалённое отключение всех или конкретного КСО |

### Уровень 3: Manual operator / systemd

| Параметр | Значение |
|---|---|
| **Механизм** | `systemctl stop kso-player` |
| **Время реакции** | < 2 сек (SIGTERM → cleanup → exit) |
| **Применение** | Экстренная остановка на конкретной КСО |
| **Восстановление** | `systemctl start kso-player` (после устранения причины) |

### Принципы kill-switch

- Kill-switch **всегда** побеждает: если любой уровень активен → player скрыт
- Kill-switch срабатывает **до** проверки state contract
- Kill-switch **не влияет** на УКМ5 (player просто исчезает)
- Kill-switch оставляет **чистый экран** (никаких артефактов)

---

## 8. Pilot Safety

### 8.1 Mandatory safety gates

| # | Правило | Enforcement |
|---|---|---|
| S1 | Не показывать во время оплаты | State = `payment` → hidden. Геометрия: overlay zone не достаёт до payment button |
| S2 | Не перекрывать кнопку оплаты | Overlay zone: y=400-640, payment button: y=720-840. Gap = 80px |
| S3 | Не перекрывать отмену/помощь | Header (y=0-60) всегда видим. Close button всегда видим |
| S4 | Не показывать при unknown/stale | State ≠ `idle` → hidden. Stale TTL = 5 сек |
| S5 | Запуск только в нерабочее окно | Первый manual smoke — ночью или в выходной |
| S6 | Сначала manual smoke без автозапуска | `systemctl start` вручную. НЕ `systemctl enable` |
| S7 | Controlled systemd только после approval | После успешного smoke + sign-off — `systemctl enable` |

### 8.2 Pilot rollout sequence

```
1. Manual smoke (off-hours)
   ├── SSH, запустить player вручную
   ├── Проверить: overlay виден в idle, скрыт при касании
   ├── Проверить: payment button не перекрыт
   ├── Проверить: kill-switch file flag работает
   └── Решение: GO / NO-GO

2. Controlled systemd (после sign-off)
   ├── `systemctl start kso-player`
   ├── Мониторинг 1 час
   └── Если OK → `systemctl enable`

3. Pilot rollout (3-5 КСО)
   ├── Установка через bootstrap
   ├── 24-72ч стабильности
   └── Production auth (P0-1, P0-2)
```

---

## 9. Implementation Steps

### 38.0.6 — Contract & Tests for Portrait Profile Geometry

- Создать `apps/kso_player/profiles/portrait_idle_overlay_768/`
- Определить dataclass `PortraitOverlayGeometry`:
  ```python
  root_w, root_h = 768, 1024
  overlay_x, overlay_y = 0, 400
  overlay_w, overlay_h = 768, 240
  canvas_x, canvas_y = 0, 420
  canvas_w, canvas_h = 768, 200
  ```
- Написать тесты: геометрия не выходит за root screen, не перекрывает payment zone
- Создать state contract dataclass + валидатор

### 38.0.7 — Player Shell Support for Non-Fullscreen Overlay Profile

- Адаптировать player shell: поддержка `profile=portrait_idle_overlay_768`
- Overlay window geometry из профиля (не fullscreen)
- X11 window hints: override-redirect, no focus, input transparent
- Тесты: shell snapshot render для portrait overlay

### 38.0.8 — Local Kill-Switch

- Проверка `/run/verny/kso/kill_switch` каждый cycle tick
- При обнаружении: unmaps window, graceful shutdown
- Тесты: kill-switch file flag → player exit with code 0

### 38.0.9 — State Observer Stub / Safe Idle-Only

- State adapter stub для `portrait_idle_overlay_768`
- Генерация safe state: только `idle` (manual) или `unknown` (default)
- Тесты: state contract валидация, forbidden fields reject

### 38.0.10 — Local Smoke on Dev Environment

- Xvfb или headless smoke: запуск player с portrait overlay profile
- Проверка: geometry correct, state transitions работают
- Проверка: kill-switch срабатывает

### 38.0.11 — Manual Test on Physical KSO

- Off-hours: запустить player на test KSO (192.168.110.223)
- Проверить: overlay в idle-зоне (y=400-640), не перекрывает payment button
- Проверить: скрытие при касании экрана
- Проверить: kill-switch file flag
- Решение: GO / NO-GO для controlled systemd

---

## 10. Что НЕ меняется

| Компонент | Статус |
|---|---|
| Backend (campaign/schedule/approval/manifest/PoP) | ✅ Без изменений |
| Portal-web (UI, RBAC, creative upload) | ✅ Без изменений |
| Sidecar agent (manifest fetch, PoP send) | ✅ Без изменений |
| State adapter (API контракт) | ✅ Без изменений (новый source для UKM5) |
| Infra (bootstrap, preflight, systemd) | ✅ Без изменений (player unit обновится под portrait профиль) |
| Landscape player (1920×1080) | 📦 Архив — не удаляется, 968 тестов зелёные |

---

## Файлы

- `docs/audit/portrait-player-profile-design.md` — этот документ
- `docs/audit/kso-portrait-architecture-pivot.md` — архитектурный pivot
- `docs/audit/ukm5-ui-safe-zone-mapping.md` — safe zone mapping
- `docs/audit/test-kso-end-to-end-readiness-gate.md` — readiness gate
- `docs/audit/technical-debt-register.md` — реестр техдолга
- `docs/audit/technical-debt-next-actions.md` — план действий
- `docs/audit/one-kso-pilot-readiness-plan.md` — план test KSO → pilot

## Журнал

### 2026-06-24 — Шаг 38.0.5

Спроектирован portrait player profile `portrait_idle_overlay_768`:
- Геометрия: overlay zone y=400-640 (768×240), creative canvas 768×200 centered
- Режимы: 9 состояний, idle-only показ, hide SLA < 500 мс
- State contract: минимальный, 5 полей, 9 разрешённых состояний
- Forbidden fields: receipt, transaction, payment, fiscal, customer, card, items, total
- Kill-switch: 3 уровня (file flag, backend command, systemctl stop)
- Pilot safety: 7 mandatory gates, 3-phase rollout
- Implementation: 6 шагов (38.0.6 — 38.0.11)

Код не менялся. КСО не менялась.
