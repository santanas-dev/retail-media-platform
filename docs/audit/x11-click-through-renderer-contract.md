# X11 Click-through Renderer Contract — `x11_click_through`

> **Статус:** 📐 Renderer Contract (38.1.6)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Определить контракт production-ready X11 click-through renderer для fullscreen idle screensaver 768×1024.
> **НЕ:** физический запуск, изменение КСО, имплементация X11-клиента.
>
> **Предыдущий шаг:** 38.1.5 — Input Pass-through Design. Decision matrix: x11_click_through recommended for production.
> **Следующий шаг:** 38.1.7 — Physical X11 renderer test на КСО.

---

## 1. Renderer Identity

| Параметр | Значение |
|---|---|
| **Renderer type** | `x11_click_through` |
| **Profile** | `portrait_fullscreen_idle_screensaver_768` |
| **Production-ready** | ✅ Да (при условии что все pass-through свойства enabled) |
| **Заменяет Chromium --app** | ✅ Да — НЕ использует Chromium |

---

## 2. Window Properties

### 2.1 Mandatory X11 properties

| Свойство | Значение | Почему |
|---|---|---|
| `override_redirect` | **True** | Bypass WM — окно не управляется Openbox |
| `always_on_top` | **True** | _NET_WM_STATE_ABOVE — всегда поверх УКМ5 |
| `input_region_empty` | **True** | XFixes empty input shape — pointer passthrough |
| `no_focus_steal` | **True** | Никогда не захватывает фокус |
| `no_keyboard_grab` | **True** | Клавиатура идёт в УКМ5 |
| `no_pointer_grab` | **True** | Тач/мышь идут в УКМ5 |

### 2.2 Geometry

```
Root:    768 × 1024
Window:  x=0, y=0, w=768, h=1024
```

### 2.3 Render pipeline (conceptual)

```
Manifest media → Pre-rendered frame (Pillow/Cairo) → X11 Pixmap → X11 window
                                                                    ├── override_redirect=True
                                                                    ├── _NET_WM_STATE_ABOVE
                                                                    ├── XFixes input shape: EMPTY
                                                                    └── NO focus / NO grab
```

---

## 3. Safety Contract

### 3.1 Input pass-through guarantees

| Аспект | Гарантия | Метод |
|---|---|---|
| **Scanner** | Не теряется | Нет keyboard focus → клавиатура идёт в УКМ5 |
| **Touch** | Не теряется | XFixes empty input shape → pointer events проходят сквозь |
| **Keyboard** | Не теряется | Нет keyboard grab → клавиатура идёт в УКМ5 |

### 3.2 Hide triggers

Окно **не участвует** в обработке ввода. Скрытие происходит через:

1. **State observer** — state ≠ idle → `XUnmapWindow`
2. **Kill-switch** — file flag → `XUnmapWindow`
3. **External command** — `XUnmapWindow` / SIGTERM

### 3.3 Production readiness

| Условие | Требование |
|---|---|
| input_region_empty | **True** (обязательно) |
| no_keyboard_grab | **True** (обязательно) |
| no_pointer_grab | **True** (обязательно) |
| no_focus_steal | **True** (обязательно) |
| override_redirect | **True** (обязательно) |
| scanner_loss_free | **True** |
| touch_loss_free | **True** |

**Production-ready = True** только если ВСЕ условия выполнены.

---

## 4. Code Contract

### 4.1 Dataclasses

| Dataclass | Назначение |
|---|---|
| `X11ClickThroughCapabilities` | Статические возможности renderer (frozen) |
| `X11RendererPlan` | Конкретный план рендеринга (frozen) |
| `X11RendererValidationResult` | Результат валидации (frozen) |

### 4.2 Функции

| Функция | Назначение |
|---|---|
| `validate_renderer_plan(plan)` | Проверяет план на соответствие контракту |
| `validate_safe_output(data)` | Проверяет отсутствие forbidden fields |
| `create_default_renderer_plan()` | Создаёт production-ready план (x11_click_through) |
| `create_wake_only_renderer_plan()` | Создаёт НЕ-production план (wake_only, для сравнения) |

### 4.3 Forbidden fields

```python
FORBIDDEN_FIELDS = {
    # Фискальные/PII
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    # Secrets
    "backend_url", "backend_host", "backend_port",
    "token", "secret", "api_key", "password", "access_token",
    "refresh_token", "bearer", "jwt",
    # Scanner
    "event_key", "event_code", "event_keycode", "event_data",
    "event_value", "input_value", "scanner_value", "barcode", "key_value",
}
```

---

## 5. Comparison: Renderer vs Chromium

| Критерий | x11_click_through | Chromium --app (wake_only) |
|---|---|---|
| **Input passthrough** | ✅ Да | ❌ Нет |
| **Scanner loss** | ✅ Нет потерь | 🔴 Теряет первый скан |
| **Touch loss** | ✅ Нет потерь | 🔴 Теряет первое касание |
| **Production-ready** | ✅ Да | ❌ Нет (test_only) |
| **Сложность реализации** | 🔴 Высокая | 🟢 Низкая |
| **Зависимости** | python3-xlib, XFixes | Chromium (уже есть) |
| **Рендеринг** | Pillow/Cairo → Pixmap | Chromium HTML/CSS |
| **Статус** | 📐 Contract defined | ✅ Реализован (test only) |

---

## 6. Roadmap

```
38.1.6 (этот документ)
  └── Renderer contract: dataclasses, validators, 79 тестов

38.1.7 — X11 Renderer Feasibility Test (будущее)
  ├── Проверить python3-xlib доступность на КСО
  ├── Проверить XFixes доступность
  ├── Создать минимальный X11 test window
  └── Подтвердить stacking поверх УКМ5

38.1.8 — Fullscreen Production Test (будущее)
  ├── Только после подтверждения pass-through
  ├── Controlled test на КСО 192.168.110.223
  └── Verify: scanner не теряется, touch проходит сквозь
```

---

## 7. Physical Proof Harness (38.1.7)

Runtime proof harness подготовлен, но **физический запуск НЕ выполнялся**.

См. `docs/audit/x11-click-through-physical-proof-plan.md`.

Код: `x11_click_through_proof.py` + `scripts/x11_click_through_proof_harness.py` (82 теста).
3 режима: dry_run, preflight_only, run_once (заблокирован до explicit approval).

## 8. Blocker Status

| ID | Название | Статус | Решение |
|---|---|---|---|
| B-FS-1 | Первый скан теряется | 🟢 **Закрыт** (X11/focus/input-path) | 38.1.8 proof. HW E2E — follow-up |
| B-FS-2 | Input passthrough невозможен с Chromium | 🟢 **Закрыт** | Отдельный X11 renderer (не Chromium) |
| B-FS-3 | Production fullscreen запрещён | 🟡 Guarded runner + HW scanner + pilot | После G6/G7 |

---

## 8. Файлы

- `docs/audit/x11-click-through-renderer-contract.md` — этот документ
- `apps/kso_player/kso_player/x11_click_through_renderer.py` — renderer contract (code)
- `apps/kso_player/tests/test_x11_click_through_renderer.py` — 79 тестов

## Журнал

### 2026-06-24 — Шаг 38.1.8 (Physical X11 Proof — SUCCESS)

Physical proof на КСО 192.168.110.223: 100% red fullscreen, XFixes input EMPTY, focus NOT stolen.
B-FS-1/B-FS-2 closed. HW scanner E2E — follow-up before pilot.

### 2026-06-24 — Шаг 38.1.6

Создан контракт X11 click-through renderer:
- Dataclasses: X11ClickThroughCapabilities, X11RendererPlan, X11RendererValidationResult (frozen)
- Validator: проверяет geometry, input pass-through, override-redirect, kill-switch, SLA
- Safe output: forbidden fields rejected
- Production-ready: true только если все pass-through свойства enabled
- Wake-only план: NOT production-ready
- 79 тестов: capabilities defaults, validation, immutability, safe output, profile alignment

КСО не менялась. Physical test не запускался. Chromium не запускался.
