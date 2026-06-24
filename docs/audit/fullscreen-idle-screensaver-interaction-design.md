# Fullscreen Idle Screensaver Interaction Design — `portrait_fullscreen_idle_screensaver_768`

> **Статус:** 📐 Interaction Design (38.1.4)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Спроектировать безопасную логику fullscreen-заставки 768×1024 для УКМ5-КСО, которая исчезает при любом касании или вводе со сканера.
> **Это новый режим — fullscreen idle screensaver, НЕ старый Zone C overlay.**
> **НЕ:** физический запуск, изменение КСО, чтение БД УКМ5.

---

## 1. Profile Identity

| Параметр | Значение |
|---|---|
| **Profile name** | `portrait_fullscreen_idle_screensaver_768` |
| **Profile code** | `portrait_fullscreen_idle_screensaver_768` |
| **Root screen** | 768 × 1024 portrait |
| **Window geometry** | x=0, y=0, w=768, h=1024 |
| **Mode** | fullscreen idle-only screensaver |
| **Display content** | Только synthetic/fullscreen ad creative |
| **Hide SLA** | ≤ 500 ms, целевое ≤ 200 ms |
| **Отличие от Zone C overlay** | Занимает **весь экран**, а не только зону y=400-640 |

### Design philosophy

> Fullscreen screensaver — это режим ожидания кассы. Когда кассир/покупатель бездействует — весь экран занят рекламой. При **любом** касании, сканировании или изменении состояния — заставка мгновенно исчезает, открывая интерфейс УКМ5.

---

## 2. Hide Triggers (полный перечень)

### 2.1 Touch/Pointer/Click

| Триггер | DOM Event | Приоритет |
|---|---|---|
| Касание экрана (touch) | `touchstart` | P0 |
| Нажатие пальцем | `pointerdown` | P0 |
| Клик мыши | `mousedown` | P0 |
| Любой клик | `click` | P0 |
| Прокрутка колесом | `wheel` | P1 |

### 2.2 Keyboard/Scanner input

| Триггер | DOM Event | Приоритет |
|---|---|---|
| Нажатие любой клавиши | `keydown` | P0 |
| Ввод текста (включая scanner wedge) | `input` | P0 |
| Штрихкод со сканера (keyboard wedge) | `keydown` + `input` | P0 |

### 2.3 State-based hide

| Триггер | Условие | Приоритет |
|---|---|---|
| Состояние ≠ idle | `state in {busy, scan, cart, payment, error, offline, unknown, stale}` | P0 |

### 2.4 Kill-switch

| Триггер | Механизм | Приоритет |
|---|---|---|
| File flag | `/run/verny/kso/kill_switch` существует | P0 |
| Backend command | Через sidecar → manifest/device command | P0 |
| systemd stop | `systemctl stop kso-player` | P0 |

---

## 3. Scanner Rule

### 3.1 Проблема

Сканер штрихкодов на КСО работает как **keyboard wedge** — эмулирует нажатия клавиш. Когда Chromium overlay активен:

- Первое сканирование может быть **перехвачено** overlay-окном (события `keydown`/`input` идут в Chromium, а не в УКМ5)
- Штрихкод будет «проглочен» заставкой и **не попадёт** в УКМ5

### 3.2 Правила безопасности

| Правило | Описание |
|---|---|
| **Не логировать** | Значение штрихкода не сохраняется, не передаётся, не пишется в логи |
| **Не сохранять** | `event.key`, `event.data`, `event.code`, `event.keyCode` — не записываются |
| **Не передавать** | Никакой backend URL, никакой API-call со значением сканера |
| **В логах только** | `input_event_detected: true` — бинарный флаг |
| **Мгновенное скрытие** | При первом `keydown`/`input` заставка немедленно скрывается |

### 3.3 Риск потери первого скана

> **BLOCKER:** Первый скан может быть перехвачен overlay и не попасть в УКМ5. Это нужно явно зафиксировать.

| Аспект | Оценка |
|---|---|
| Вероятность | **Высокая** — Chromium `--app` окно захватывает keyboard input |
| Влияние на UX | **Значительное** — кассиру придётся сканировать товар дважды |
| Влияние на бизнес | **Умеренное** — задержка ~1-2 секунды на первом товаре после idle |
| Категория | **UX blocker** — необходимо решить до production |

---

## 4. Два варианта решения

### 4.1 Вариант A: Wake-only

**Логика:** первое касание/сканирование **только убирает заставку**. Пользователь должен повторить действие.

```
Покупатель касается экрана
  → заставка скрывается (hide SLA ≤ 500ms)
  → УКМ5 виден
  → покупатель касается снова (второй раз) — теперь уже УКМ5
```

```
Кассир сканирует товар
  → сканер эмулирует keystrokes
  → заставка перехватывает события, скрывается
  → штрихкод ПОТЕРЯН
  → кассир должен отсканировать повторно
```

| Плюсы | Минусы |
|---|---|
| Простая реализация | Плохой UX — двойное действие |
| Нет риска гонки событий | Первый скан теряется гарантированно |
| Не зависит от WM/Chromium версии | Раздражает кассиров |

### 4.2 Вариант B: Pass-through preferred

**Логика:** заставка скрывается, **а ввод передаётся дальше** в УКМ5.

```
Кассир сканирует товар
  → сканер эмулирует keystrokes
  → заставка перехватывает первое событие
  → заставка скрывается + forward события в УКМ5
  → УКМ5 получает штрихкод
  → товар добавлен в чек
```

**Проблема реализации с Chromium overlay:**

| Механизм | Возможно? | Почему |
|---|---|---|
| Chromium `--app` input passthrough | ❌ | Chromium захватывает input; нет API для forward в другое окно |
| X11 `XIAllowEvents` + `ReplayDevice` | ⚠️ | Теоретически возможно с X11 grab + replay, но сложно и хрупко |
| X11 override-redirect + input passthrough | ✅ | Окно без захвата ввода; клавиатура идёт напрямую в УКМ5 |
| State-based hide без перехвата | ✅ | Sidecar/state adapter видит смену состояния → скрывает заставку; клавиатура не перехватывается |

**Рекомендация:** вариант B через **state-based hide** (сторонний observer видит `state ≠ idle` и скрывает заставку) + X11 click-through для touch. Это означает:

- Chromium overlay не захватывает клавиатуру (input transparent)
- State adapter на КСО мониторит состояние УКМ5
- При `state → busy/scan` заставка скрывается через window manager
- Сканер работает напрямую с УКМ5, штрихкод не теряется

### 4.3 Выбор варианта

| Вариант | Рекомендация | Статус |
|---|---|---|
| A (Wake-only) | Простой fallback | ⬜ Запасной |
| B (Pass-through) | **Целевой** | ⬜ Требует отдельного design step для X11 pass-through |

---

## 5. Interaction Hide Rules — формальный контракт

### 5.1 Hide Rule — структура данных

```python
class HideRule:
    trigger: str        # "touchstart" | "pointerdown" | "mousedown" | "click" |
                        # "keydown" | "input" | "wheel" |
                        # "state_change" | "kill_switch"
    priority: int       # 0 = highest
    hide_target_ms: int # целевое время скрытия
    passthrough: bool   # True если ввод должен пройти дальше
```

### 5.2 Правила (приоритет → выше приоритетнее)

| # | Trigger | Priority | Target (ms) | Passthrough | Примечание |
|---|---|---|---|---|---|
| 1 | `kill_switch` | 0 | 200 | N/A | Всегда побеждает |
| 2 | `state_change` | 1 | 500 | Yes | State adapter сигнал |
| 3 | `keydown` | 2 | 200 | **No** (риск потери) | Scanner wedge |
| 4 | `input` | 2 | 200 | **No** (риск потери) | Scanner wedge |
| 5 | `touchstart` | 3 | 200 | **Yes** (желательно) | Касание экрана |
| 6 | `pointerdown` | 3 | 200 | **Yes** (желательно) | Касание экрана |
| 7 | `mousedown` | 3 | 200 | **Yes** (желательно) | Клик |
| 8 | `click` | 4 | 200 | **Yes** (желательно) | Любой клик |
| 9 | `wheel` | 5 | 300 | **Yes** (желательно) | Прокрутка |

### 5.3 Hide Contract — функция

```python
def should_hide(
    dom_events: set[str],       # активные DOM-события с последнего tick
    state: str,                  # текущее состояние УКМ5
    kill_switch_active: bool,    # флаг kill-switch
    stale_sec: float = 0.0,      # возраст последнего state-сигнала
) -> HideDecision:
    """
    HideDecision:
        hide: bool               # нужно ли скрыть заставку
        reason: str              # причина: "kill_switch" | "state_change" |
                                 #           "keydown" | "touchstart" | ...
        target_ms: int           # целевое время скрытия
        passthrough: bool        # нужно ли пробросить ввод дальше
        scanner_risk: bool       # есть ли риск потери сканера
    """
```

### 5.4 Приоритеты разрешения конфликтов

```
kill_switch > state_change > keydown/input > touch/pointer/mouse > click > wheel
```

Если одновременно сработали `keydown` и `touchstart` → побеждает `keydown` (выше приоритет).

---

## 6. Безопасность данных

### 6.1 Что НЕ сохраняется

| Данные | Правило |
|---|---|
| `event.key` | ❌ Не сохраняется |
| `event.code` | ❌ Не сохраняется |
| `event.keyCode` | ❌ Не сохраняется |
| `event.data` | ❌ Не сохраняется |
| `event.target.value` | ❌ Не сохраняется |
| Штрихкод | ❌ Не логируется, не передаётся |
| Key events | ❌ Не сохраняются |
| Scanner input | ❌ Не сохраняется |

### 6.2 Что разрешено в логах

| Поле | Значение |
|---|---|
| `input_event_detected` | `true` / `false` |
| `hide_trigger` | `"keydown"`, `"touchstart"`, etc. |
| `hide_target_ms` | Число |
| `hide_actual_ms` | Число |
| `scanner_risk` | `true` / `false` |

---

## 7. Blockers (добавлены в другие документы)

| # | Блокер | Серьёзность | Статус |
|---|---|---|---|
| B-FS-1 | **Первый скан теряется** при fullscreen Chromium overlay | 🔴 BLOCKER | Требует X11 pass-through design |
| B-FS-2 | **Input passthrough невозможен** с Chromium `--app` | 🔴 BLOCKER | Требует отдельного design step |
| B-FS-3 | **Production fullscreen mode запрещён** до решения scanner/touch wake behaviour | 🔴 BLOCKER | Ждёт B-FS-1, B-FS-2 |

---

## 8. Связь с существующими профилями

| Профиль | Режим | Геометрия | Статус |
|---|---|---|---|
| `portrait_idle_overlay_768` | Zone C overlay | (0,400) 768×240 | ✅ Реализован, Phase 1–2 пройдены |
| `portrait_fullscreen_idle_screensaver_768` | Fullscreen screensaver | (0,0) 768×1024 | 📐 Design (этот документ) |

**Важно:** новый профиль **не заменяет** Zone C overlay. Это отдельный режим для другого сценария использования. Zone C overlay остаётся основным v1 production профилем.

---

## 9. Implementation Sequence

```
38.1.4 — Interaction Design (этот документ)
  ├── Profile contract: portrait_fullscreen_idle_screensaver_768
  ├── Interaction hide rules: interaction_hide.py
  ├── Tests: profile contract + hide rules
  └── Docs update: 6 files

38.1.5 — X11 Pass-through Design (будущее)
  ├── Исследовать X11 input grab + replay
  ├── Проверить click-through с override-redirect
  ├── Снять blocker B-FS-2

38.1.6 — Physical Fullscreen Test (будущее)
  ├── Только после решения pass-through
  └── Отдельный controlled experiment на КСО
```

---

## 10. Файлы

- `docs/audit/fullscreen-idle-screensaver-interaction-design.md` — этот документ
- `apps/kso_player/kso_player/profiles/portrait_fullscreen_idle_screensaver_768.py` — profile contract
- `apps/kso_player/kso_player/interaction_hide.py` — hide rules (будущий)
- `apps/kso_player/tests/test_profile_fullscreen_idle_screensaver_768.py` — тесты профиля
- `apps/kso_player/tests/test_interaction_hide.py` — тесты hide rules (будущий)

## Журнал

### 2026-06-24 — Шаг 38.1.4

Создан design-документ для fullscreen idle screensaver interaction:
- Profile `portrait_fullscreen_idle_screensaver_768`: 768×1024, fullscreen, idle-only
- 9 hide triggers: touch, pointer, mouse, click, keydown, input, wheel, state_change, kill_switch
- Scanner rule: keyboard wedge → мгновенное скрытие, значение не логируется
- Blocker: первый скан теряется при Chromium overlay
- Два варианта: wake-only (простой) vs pass-through (целевой)
- Приоритеты: kill_switch > state_change > keydown/input > touch/pointer/mouse > click > wheel
- Hide SLA: ≤ 500 ms, target ≤ 200 ms

Код профиля и тесты — следующий шаг.
КСО не менялась. Physical fullscreen test не запускался.
