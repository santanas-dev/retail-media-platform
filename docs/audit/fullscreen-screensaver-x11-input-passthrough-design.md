# Fullscreen Screensaver — X11 Input Pass-through / Click-through Design

> **Статус:** 📐 Architecture Design — Input Mode Selection (38.1.5)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Спроектировать безопасный механизм fullscreen-заставки 768×1024, которая видна поверх УКМ5 kiosk, но не перехватывает ввод пользователя — либо прозрачна для событий, либо мгновенно скрывается без потери данных.
> **НЕ:** физический запуск, изменение КСО, чтение БД УКМ5.
>
> **Предыдущий шаг:** 38.1.4 — Interaction Design. Profile `portrait_fullscreen_idle_screensaver_768`, 9 hide triggers, scanner safety, 141 тест.
> **Критический риск:** B-FS-1 — первый скан теряется при Chromium `--app` overlay.
> **Целевой вариант:** pass-through (B) vs запасной wake-only (A).

---

## 1. Problem Statement

```
Кассир на КСО с УКМ5 сканирует товар:

    Chromium --app fullscreen overlay (PID X, окно 768×1024 на всём экране)
    Сканер эмулирует клавиатуру → keydown/input события
    Chromium overlay ПЕРЕХВАТЫВАЕТ события (окно имеет фокус)
    Заставка скрывается
    НО: штрихкод УЖЕ ПОТЕРЯН — не дошёл до УКМ5

Результат: кассиру нужно сканировать товар повторно.
```

**Корень проблемы:** Chromium `--app` окно создаётся как обычное окно X11 — оно получает keyboard focus и захватывает все keystrokes. Даже если мы мгновенно скроем окно в обработчике `keydown`, само значение штрихкода уже ушло в Chromium, а не в УКМ5.

---

## 2. Environment Constraints

| Параметр | КСО (192.168.110.223) | Dev (localhost) |
|---|---|---|
| **OS** | Ubuntu 18.04.6 | Ubuntu 24.04 |
| **Kernel** | 5.4.0-100 | 6.8.0 |
| **Xorg** | X.Org (standard) | X.Org / Wayland |
| **WM** | Openbox 3.6.1 | N/A |
| **Chromium** | v114 (2018 era) | v120+ |
| **libXfixes** | ✅ installed | ✅ installed |
| **python3-xlib** | ⚠️ нужно установить | ⚠️ нужно установить |
| **xdotool** | ✅ available | ✅ available |
| **wmctrl** | ⚠️ нужно установить | ✅ available |

---

## 3. Input Mode Options — Analysis

### 3.1 Option A: Chromium Overlay Wake-Only

**Механизм:** Chromium `--app` fullscreen окно ловит первый input → вызывает `hide()` → окно скрывается. Пользователь повторяет действие.

```
Сканер → Chromium overlay получает keydown → hide() → штрихкод ПОТЕРЯН → сканировать заново
Касание → Chromium overlay получает touchstart → hide() → коснуться снова
```

| Критерий | Оценка |
|---|---|
| Видно поверх УКМ5 | ✅ Да (с windowraise) |
| Не теряет первый скан | ❌ **НЕТ — теряет гарантированно** |
| Не перехватывает touch | ❌ Перехватывает (нужно второе касание) |
| Не требует изменений УКМ5 | ✅ Нет |
| Не требует чтения БД | ✅ Нет |
| Сложность реализации | 🟢 Минимальная |
| Риски для магазина | 🔴 **Высокие** — повторное сканирование каждого товара |
| Пригодность для pilot | 🔴 **НЕТ** — неприемлемый UX |

**Вердикт:** допустим только как **test_only** / **not_production_ready**. Для production непригоден.

---

### 3.2 Option B: Chromium Overlay with Focus Return

**Механизм:** overlay ловит события → мгновенное скрытие → `xdotool windowactivate` на УКМ5. Надежда: пользователь не отпустил сканер, повторный ввод уйдёт уже в УКМ5.

```
Сканер → Chromium overlay keydown → hide() → windowactivate UKM5
→ если сканер всё ещё шлёт данные (многократные keystrokes) → УКМ5 получает остаток
→ первый символ/нажатие ПОТЕРЯН
```

| Критерий | Оценка |
|---|---|
| Видно поверх УКМ5 | ✅ Да |
| Не теряет первый скан | ⚠️ **ЧАСТИЧНО** — зависит от сканера |
| Не перехватывает touch | ❌ Перехватывает первое касание |
| Не требует изменений УКМ5 | ✅ Нет |
| Не требует чтения БД | ✅ Нет |
| Сложность реализации | 🟡 Средняя |
| Риски для магазина | 🟠 **Средние** — race condition scan-vs-hide |
| Пригодность для pilot | 🟡 **Условно** — зависит от таймингов сканера |

**Технический анализ:**
- Сканер-клин (barcode wedge) обычно шлёт данные одним burst'ом из 8-13 символов + Enter
- Типичная скорость: 50-200 символов/сек
- Время между первым keydown и hide() = ~50-200 мс (Chromium JS → IPC → X11 unmap)
- К моменту hide() сканер мог отправить 3-10 символов из 13
- Остаток burst'а (3-10 символов) уходит уже в несуществующее окно (overlay unmapped)
- `windowactivate UKM5` возвращает фокус, но сканер УЖЕ закончил отправку

**Вывод:** даже с мгновенным hide + focus return, первый скан **почти наверняка теряется полностью**. Сканер не ждёт — burst происходит быстрее, чем X11 успевает переключить фокус.

**Вердикт:** непригоден для production. Теряет первый скан так же, как wake-only.

---

### 3.3 Option C: X11 Override-Redirect Transparent/Click-through Overlay

**Механизм:** X11 окно с флагом `override-redirect` + input region empty. Окно **видимо**, но **не участвует в обработке ввода**. Все события (клавиатура, мышь, тач) проходят напрямую в нижележащее окно УКМ5.

```
X11 Override-Redirect окно:
    - override_redirect = True         # WM не управляет
    - input_shape = EMPTY_REGION       # XFixes SetWindowShapeRegion с пустым bounding
    - _NET_WM_STATE_ABOVE              # Висит над УКМ5
    - Не получает фокус
    - Не получает клавиатуру/мышь/тач

Сканер → keystrokes идут НАПРЯМУЮ в УКМ5 (фокус не уходит)
Касание → touch events идут НАПРЯМУЮ в УКМ5
Заставка → видна и не мешает
```

| Критерий | Оценка |
|---|---|
| Видно поверх УКМ5 | ✅ Да (override-redirect + ABOVE) |
| Не теряет первый скан | ✅ **ДА — не перехватывает** |
| Не перехватывает touch | ✅ **ДА — прозрачно** |
| Не требует изменений УКМ5 | ✅ Нет |
| Не требует чтения БД | ✅ Нет |
| Сложность реализации | 🔴 **Высокая** |
| Риски для магазина | 🟠 **Средние** — stacking, repaint |
| Пригодность для pilot | 🟢 **ДА — целевой вариант** |

**Технический анализ:**

**Проблема 1 — Override-redirect vs Stacking:**
- Override-redirect окна не управляются WM (Openbox)
- Их Z-order может быть недетерминированным
- UKM5 kiosk (Chromium с `--kiosk`) может иметь `_NET_WM_STATE_FULLSCREEN`, что даёт ему повышенный приоритет
- **Решение:** `XRaiseWindow` + `XConfigureWindow` с `Above` в цикле (каждые 500ms) или через `_NET_WM_STATE_ABOVE`

**Проблема 2 — Input Shape (XFixes):**
- `XFixesCreateRegion` + `XFixesSetWindowShapeRegion` с пустым bounding box
- Доступно в libXfixes (уже есть на КСО)
- **НО:** влияет только на pointer events (мышь/тач). **Клавиатура НЕ фильтруется через input shape** — она идёт в окно с фокусом.
- Если overlay не имеет фокуса (override-redirect окна обычно не получают фокус) — клавиатура уходит в активное окно (УКМ5 Chromium kiosk)
- **Проверка:** на Openbox + Xorg, override-redirect окно без фокуса → клавиатура идёт в kiosk

**Проблема 3 — Chromium vs X11 Client:**
- Chromium `--app` **не может** быть override-redirect (это свойство X11-уровня, не HTTP)
- Нужен **отдельный рендерер**: либо Python с Xlib + Cairo, либо легковесный X11-клиент
- Альтернатива: MPV с `--ontop --no-focus --input-ipc-server=` (не захватывает клавиатуру)

**Проблема 4 — Python 3.6.9 на КСО:**
- python3-xlib доступен через `apt install python3-xlib` (Ubuntu 18.04)
- Cairo/Pango для рендеринга HTML-подобного контента сложны
- **Проще:** использовать Chromium в headless + скриншот → отображать как X11 Pixmap (офлайн)

**Вердикт:** технически возможен, но требует:
1. Отдельного X11-клиента (не Chromium) для рендеринга
2. XFixes для прозрачности pointer-событий
3. Override-redirect для bypass WM
4. Отсутствия фокуса для keyboard pass-through

Это **значительный объём разработки**, выходящий за рамки текущего этапа. **Рекомендуется как целевой для последующего шага 38.1.6.**

---

### 3.4 Option D: XShape/XFixes Input Region Empty

**Механизм:** то же, что вариант C, но с акцентом на XFixes `SetWindowShapeRegion` с пустым регионом. Это специализация варианта C — детальный разбор feasibility на целевом окружении.

```
Окно: Chromium --app ИЛИ X11 client
    XFixesSetWindowShapeRegion(window, ShapeInput, 0, 0, EMPTY_REGION)
    → pointer events проходят сквозь окно
    → keyboard: окно без фокуса → идёт в УКМ5
```

| Аспект | Chromium --app | X11 client (python-xlib) |
|---|---|---|
| Можно ли задать override-redirect? | ❌ Нет (не управляется извне) | ✅ Да |
| Можно ли задать input shape? | ❌ Нет (Chromium не экспонирует) | ✅ Да (XFixes API) |
| Можно ли гарантировать above? | ⚠️ xdotool windowraise | ✅ XRaiseWindow |
| Сложность рендеринга HTML | 🟢 Встроен | 🔴 Нужен кастомный рендерер |
| Сложность интеграции | 🟢 Минимальная | 🔴 Высокая |

**Вывод:** с Chromium `--app` вариант D недоступен (нет API для XFixes). С X11-клиентом — доступен, но требует реализации рендерера.

**Вердикт:** **целевой для post-pilot.** Требует отдельного этапа разработки X11-клиента с XFixes pass-through.

---

### 3.5 Option E: State-Based Hide Without Keyboard Capture

**Механизм:** заставка **не перехватывает** сканер. Observer на КСО мониторит состояние УКМ5 через безопасный источник. При `state → busy/scan` заставка скрывается через window manager.

```
Observer (state_adapter) мониторит:
    - /proc/*/fd доступ к файлам УКМ5 (read-only, без содержимого)
    - X11 _NET_ACTIVE_WINDOW (изменилось ли активное окно)
    - DBus сигналы (если УКМ5 их шлёт)
    - Системные события (не чтение БД, не чтение чеков)

При state != idle → observer сигналит → hide заставки
```

| Критерий | Оценка |
|---|---|
| Видно поверх УКМ5 | ✅ Да (если stacking решён) |
| Не теряет первый скан | ✅ **ДА — не перехватывает** |
| Не перехватывает touch | ✅ Да |
| Не требует изменений УКМ5 | ✅ Нет |
| Не требует чтения БД | ✅ Нет |
| Сложность реализации | 🟡 Средняя |
| Риски для магазина | 🟢 **Низкие** |
| Пригодность для pilot | 🟢 **ДА — перспективный** |

**Технический анализ:**

**Доступные источники состояния без чтения БД/чеков:**

| Источник | Что даёт | Безопасность | Скорость |
|---|---|---|---|
| `xdotool getactivewindow` | Изменилось ли активное окно | ✅ Read-only | ~50ms |
| `xprop -id $WID _NET_WM_NAME` | Название окна УКМ5 | ✅ Read-only | ~30ms |
| `/proc/$UKM5_PID/fd/` | Активность файловых дескрипторов | ✅ Read-only | ~10ms |
| `inotify` на `/run/verny/kso/` | Внешний сигнал от state_adapter | ✅ Read-only | ~5ms |
| DBus `org.freedesktop.ScreenSaver` | Активность пользователя | ✅ Read-only | Instant |

**Лучший подход:** state_adapter (уже существующий) пишет `state.json` в `/run/verny/kso/`. Player читает этот файл. При `state ≠ idle` → hide.

**Задержка:** state_adapter polling cycle = 500-1000ms. Это МЕНЬШЕ, чем время между бездействием кассира и началом сканирования (~2-5 секунд). **Но для мгновенного touch-hide этот вариант не подходит** — touch нужно обрабатывать мгновенно.

**Гибридный подход (State + Touch):**
- **Touch/click** → обрабатывается через X11 pass-through (вариант D) — мгновенно
- **Scanner** → обрабатывается через state observer (изменение состояния) — без потери скана
- **Keyboard (не сканер)** → обрабатывается через X11 pass-through

**Вердикт:** перспективный, но требует комбинации с вариантом D для полного покрытия. **Рекомендуется как часть гибридного решения.**

---

## 4. Decision Matrix

| Критерий | A: Wake-only | B: Focus Return | C: Override-Redirect | D: XFixes Input | E: State-Based |
|---|---|---|---|---|---|
| **Видно поверх УКМ5** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Не теряет первый скан** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Не перехватывает touch** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Не требует изменений УКМ5** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Не требует чтения БД** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Сложность реализации** | 🟢 | 🟡 | 🔴 | 🔴 | 🟡 |
| **Риски для магазина** | 🔴 | 🟠 | 🟠 | 🟠 | 🟢 |
| **Пригодность для pilot** | ❌ | ❌ | 🟢 | 🟢 | 🟢 |
| **Production readiness** | ❌ | ❌ | ⬜ (шаг 38.1.6) | ⬜ (шаг 38.1.6) | 🟡 (hybrid) |

---

## 5. Recommendation: Hybrid Approach

**Target (production):** X11 Override-Redirect + XFixes + State Observer Hybrid

```
┌──────────────────────────────────────────────────────────┐
│  Idle screensaver (fullscreen, visible)                  │
│                                                          │
│  X11 override-redirect окно:                              │
│    - Z-order: ABOVE UKM5                                 │
│    - Input: XFixes empty shape (pointer passthrough)     │
│    - Focus: NEVER (keyboard → UKM5)                      │
│                                                          │
│  State observer:                                         │
│    - Мониторит state.json (/run/verny/kso/)              │
│    - state ≠ idle → unmap окна                            │
│                                                          │
│  Kill-switch:                                            │
│    - Файл /run/verny/kso/kill_switch → unmap             │
└──────────────────────────────────────────────────────────┘

Преимущества:
  1. Сканер → НЕ перехватывается (нет фокуса) → штрихкод в УКМ5
  2. Touch → НЕ перехватывается (input shape empty) → касание в УКМ5
  3. State change → observer скрывает заставку → чисто
  4. Kill-switch → мгновенное скрытие
```

**Pilot (MVP):** State-based hide + wake-only touch (временно)

```
На период pilot:
  - Заставка показывается через Chromium --app
  - Touch/keydown → заставка скрывается
  - Сканер → state observer замечает busy → скрытие
  - Риск: touch требует второго касания (wake-only)
  - Риск: если кассир СРАЗУ сканирует после idle — возможна гонка
```

**Post-pilot (production):** X11 pass-through renderer

```
Шаг 38.1.6:
  - Разработать lightweight X11-клиент (python-xlib + Cairo/Pillow)
  - XFixes input shape empty
  - Override-redirect + ABOVE stacking
  - Рендеринг: pre-rendered изображения (manifest уже содержит media URLs)
  - Или: Chromium headless → скриншот → X11 Pixmap
```

---

## 6. Input Mode Contract

### 6.1 Input modes

```python
INPUT_MODE_WAKE_ONLY        = "wake_only"         # A — test only, NOT production
INPUT_MODE_FOCUS_RETURN     = "focus_return"       # B — устаревший, не рекомендуется
INPUT_MODE_X11_CLICK_THROUGH = "x11_click_through"  # D — целевой (post-pilot)
INPUT_MODE_STATE_ONLY       = "state_only"         # E — MVP для pilot
```

### 6.2 Production readiness rules

```python
PRODUCTION_READY_MODES = frozenset({
    "x11_click_through",   # Требует X11 client implementation (step 38.1.6)
})

PILOT_READY_MODES = frozenset({
    "state_only",           # State-based hide, приемлемо для пилота
    "x11_click_through",    # Целевой для production
})

TEST_ONLY_MODES = frozenset({
    "wake_only",            # Теряет первый скан — test only
    "focus_return",         # Теряет первый скан — не рекомендуется
})
```

### 6.3 Fullscreen profile input mode

```python
# Current: not production-ready (wake_only default)
FULLSCREEN_INPUT_MODE = "wake_only"  # TODO: upgrade to "state_only" for pilot,
                                     #        then "x11_click_through" for production

def is_production_ready(input_mode: str) -> bool:
    return input_mode in PRODUCTION_READY_MODES

def is_pilot_ready(input_mode: str) -> bool:
    return input_mode in PILOT_READY_MODES
```

---

## 7. Implementation Roadmap

```
38.1.5 (этот документ)
  └── Input mode selection + decision matrix + contract

38.1.6 — X11 Pass-through Renderer (будущее)
  ├── lightweight X11 client (python-xlib + Pillow)
  ├── XFixes input shape empty
  ├── Override-redirect + ABOVE stacking
  ├── Pixel buffer from pre-rendered image
  └── Physical test: verify сканер не теряется

38.1.7 — State Observer Fast Path (будущее)
  ├── Optimise state_adapter polling (500ms → 100ms)
  ├── inotify-based trigger вместо polling
  └── Integration test: scanner → state change → hide latency

38.1.8 — Fullscreen Pilot Test (будущее)
  ├── Только после 38.1.6 или 38.1.7
  ├── Controlled test на КСО 192.168.110.223
  └── Verify: не теряется сканер, не перехватывается touch
```

---

## 8. Blockers

| ID | Название | Статус | Решение |
|---|---|---|---|
| B-FS-1 | Первый скан теряется при Chromium overlay | 🔴 OPEN | 38.1.6 (X11 pass-through) или 38.1.7 (state observer) |
| B-FS-2 | Input passthrough невозможен с Chromium --app | 🔴 OPEN | 38.1.6 (отдельный X11 renderer) |
| B-FS-3 | Production fullscreen mode запрещён | 🔴 OPEN | Ждёт B-FS-1 и B-FS-2 |

---

## 9. Файлы

- `docs/audit/fullscreen-screensaver-x11-input-passthrough-design.md` — этот документ
- `docs/audit/fullscreen-idle-screensaver-interaction-design.md` — предыдущий design (38.1.4)
- `apps/kso_player/kso_player/profiles/portrait_fullscreen_idle_screensaver_768.py` — profile contract
- `apps/kso_player/kso_player/interaction_hide.py` — hide rules engine
- `apps/kso_player/tests/test_profile_portrait_fullscreen_idle_screensaver_768.py` — тесты профиля

## Журнал

### 2026-06-24 — Шаг 38.1.5

Спроектирован механизм input pass-through для fullscreen idle screensaver:
- Разобраны 5 вариантов: A (wake-only), B (focus return), C (override-redirect), D (XFixes input), E (state-based)
- Decision matrix: A ❌, B ❌, C ✅, D ✅, E ✅
- Рекомендован гибрид: X11 override-redirect + XFixes (production) + state observer (pilot)
- Добавлен `input_mode` contract: wake_only | focus_return | x11_click_through | state_only
- Wake_only/focus_return помечены как test_only / not_production_ready
- Production-ready: только x11_click_through (требует шага 38.1.6)
- Pilot-ready: state_only или x11_click_through

КСО не менялась. Physical test не запускался.
