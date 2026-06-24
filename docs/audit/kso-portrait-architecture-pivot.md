# KSO Architecture Pivot — Portrait 768×1024 UKM5 Fleet

> **Статус:** 🔄 Architecture Pivot Decision (38.0.3-pivot)
>
> Дата: 2026-06-23
> Ревизия: 4 (38.0.6 — profile contract implemented)
>
> **Portrait Player Design (38.0.5):** завершён. Profile `portrait_idle_overlay_768`.
> Overlay zone y=400-640 (768×240), creative canvas 768×200 centered.
> См. `docs/audit/portrait-player-profile-design.md`.

---

**Safe Zone Mapping (38.0.4):** завершён. Рекомендована Zone C (Product Grid, y=400-640, 768×240).

---

> **Назначение:** Зафиксировать архитектурный разворот: v1 должен работать на реальных КСО сети — 768×1024 portrait с УКМ5 fullscreen kiosk.
> **НЕ:** изменение кода, установка на КСО, перезапуск сервисов.
>
> **Документы цепочки:**
> - Safe Zone Mapping: `docs/audit/ukm5-ui-safe-zone-mapping.md`
> - Portrait Player Design: `docs/audit/portrait-player-profile-design.md`

---

## 1. Факт

### test KSO репрезентативна для всей сети

По результатам физического аудита (38.0.1, 38.0.2) и user clarification (38.0.3-pivot):

| Параметр | test KSO (192.168.110.223) | Вся сеть |
|---|---|---|
| ОС | Ubuntu 18.04.6 | Ubuntu 18.04.6 |
| Кассовая система | СуперМаг УКМ 5 | СуперМаг УКМ 5 |
| Экран | 768×1024 портрет | 768×1024 портрет |
| Chromium | `--kiosk`, 768×1024, локальный HTML | `--kiosk`, 768×1024, локальный HTML |
| Window Manager | Openbox 3.6.1 | Openbox (предположительно) |
| Интернет | Изолированный контур | Изолированный контур |

**Вывод:** физическая test KSO **не является исключением** — вся сеть использует идентичную конфигурацию.

### Старая гипотеза неверна для v1

| Гипотеза (старая) | Реальность |
|---|---|
| Экран 1920×1080 ландшафт | 768×1024 **портрет** |
| Ad zone 1440×1080 + UKM zone 480×1080 | УКМ5 занимает **весь экран** |
| Отдельный Chromium для рекламы | Один Chromium в kiosk для всего |
| УКМ 4 | УКМ **5** |

---

## 2. Что меняется

| Компонент | Статус |
|---|---|
| Landscape split 1920 player (`kso_player` с геометрией 1440+480) | ❌ **Снят как v1 target** |
| Portrait overlay/profile player | 🆕 **Новый v1 target** |
| Backend (campaign/schedule/approval/manifest/PoP) | ✅ Без изменений — остаётся центром управления |
| Portal (creative upload, RBAC, UI) | ✅ Без изменений |
| Sidecar (manifest fetch, PoP send) | ✅ Без изменений — API-контракт не затрагивает геометрию |
| State adapter (UKM5 state discovery) | ✅ Без изменений — адаптируется под УКМ5, не под геометрию |
| Deployment artifacts (bootstrap, preflight, systemd) | ⚠️ Системные unit'ы пригодны; player unit потребует обновления профиля |

**Суть pivot'а:** меняется только **исполнительный слой показа на КСО** (player). Всё остальное — backend, portal, sidecar, state adapter, manifest, PoP — остаётся неизменным и актуальным.

---

## 3. Что НЕ выбираем

| Вариант | Причина |
|---|---|
| СуперМаг DS как primary path | Не подтверждено наличие on-premise DS. Может быть secondary при обнаружении |
| Второй fullscreen Chromium | Конфликт за экран и GPU, риск OOM, кассовый UI будет перекрыт |
| Изменение УКМ5 HTML/index.html | Без согласования с поставщиком — риск потери поддержки и сертификации ККТ |
| Overlay поверх критичных элементов | Нельзя перекрывать оплату, отмену, помощь, сканирование |
| Замена/остановка УКМ5 kiosk | Production кассовая система — остановка недопустима |

---

## 4. Новая целевая архитектура v1

```
Retail Media Portal (backend + portal-web)
    │
    ├── Campaign / Creative / Schedule / Approval / Manifest / PoP
    │   (без изменений)
    │
    ├── Sidecar Agent (manifest fetch, PoP send)
    │   (API-контракт без изменений)
    │
    ├── State Adapter (UKM5 safe state)
    │   (адаптирован под УКМ5, без чековых/платёжных данных)
    │
    └── Portrait Player Profile (НОВЫЙ)
        ├── 768×1024 portrait geometry
        ├── Не fullscreen — overlay / виджет / idle-зона
        ├── Не ломает УКМ5 kiosk
        ├── Kill-switch
        ├── Быстрое скрытие
        ├── Не перекрывает критические UI-зоны УКМ5
        ├── Read-only (не пишет в УКМ5, не читает чеки/платежи)
        └── PoP writer → sidecar → backend
```

---

## 5. Требования к portrait player (v1)

### Обязательные (P0)

| # | Требование | Обоснование |
|---|---|---|
| P0-1 | **Не fullscreen поверх УКМ5** | Кассовый интерфейс должен быть виден |
| P0-2 | **Не ломает УКМ5 kiosk** | Не конкурирует за X-дисплей, не меняет фокус |
| P0-3 | **Kill-switch** | В любой момент можно отключить без влияния на кассу |
| P0-4 | **Быстрое скрытие (< 500 мс)** | При касании экрана / начале чека — мгновенно скрыться |
| P0-5 | **Не перекрывает критичные зоны** | Оплата, отмена, помощь, сканирование — всегда видимы |
| P0-6 | **Не читает чеки, платежи, фискальные и персональные данные** | Категорический запрет |
| P0-7 | **Работает в изолированном контуре** | Без интернета, без внешних зависимостей |
| P0-8 | **PoP-отчётность** | Каждый факт показа фиксируется и доставляется через sidecar |

### Желательные (P1)

| # | Требование | Обоснование |
|---|---|---|
| P1-1 | Запуск только после safety validation | Проверка, что УКМ5 работает, критические зоны не перекрыты |
| P1-2 | Автоматический переход idle ↔ active | По сигналу от state adapter (не по чекам) |
| P1-3 | Graceful degradation при ошибках | Не крашится, не зависает, не оставляет артефактов на экране |

---

## 6. Открытые вопросы (требуют 38.0.4 — Safe Zone Mapping)

| # | Вопрос | Почему важно |
|---|---|---|
| Q1 | **Где безопасная рекламная зона на 768×1024?** | Нужно визуально определить на реальном экране |
| Q2 | Можно ли показывать рекламу только в режиме ожидания? | Самый безопасный вариант — не конкурировать с кассовым UI |
| Q3 | Как безопасно определить idle/busy без чековых данных? | State adapter должен давать сигнал, не читая чеки |
| Q4 | Overlay или отдельный режим ожидания? | Overlay-окно поверх УКМ5 vs скринсейвер при idle |
| Q5 | Можно ли использовать окно Chromium УКМ5 или нужен отдельный renderer? | Один процесс vs два — безопасность, ресурсы, конфликты |
| Q6 | Какие зоны интерфейса УКМ5 нельзя перекрывать? | Требует визуального mapping'а на реальном экране |
| Q7 | Какой механизм показа: X11 overlay / встройка в Chromium / внешний HDMI overlay? | Разные риски, разная сложность |
| Q8 | Поддерживает ли УКМ5 API для внешнего управления экраном? | Запрос поставщику |

---

## 7. Следующий безопасный шаг

### 38.0.4 — UKM5 UI Safe Zone Mapping

**Только read-only визуальный/технический mapping:**

1. Сделать screenshot экрана через VNC (`x11vnc` уже работает на порту 5900)
2. Определить критичные UI-зоны: оплата, отмена, помощь, сканирование, итог
3. Предложить 2–3 варианта безопасной рекламной зоны (сверху, снизу, idle-экран)
4. Оценить размеры и пропорции каждой зоны
5. **Ничего не менять на КСО**

---

## 8. Влияние на документацию

### Обновлённые/созданные документы

| Документ | Изменение |
|---|---|
| `kso-portrait-architecture-pivot.md` | **Новый** — этот документ |
| `test-kso-end-to-end-readiness-gate.md` | Обновлён: снята landscape геометрия, добавлена portrait |
| `test-kso-deployment-dry-run.md` | Обновлён: player unit помечен как требующий обновления профиля |
| `technical-debt-register.md` | Обновлён: P0-4 переформулирован под fleet, добавлен P0-5 (portrait player requirements) |
| `technical-debt-next-actions.md` | Обновлён: приоритет — portrait player design |
| `one-kso-pilot-readiness-plan.md` | Обновлён: v1 target = portrait 768×1024 |
| `ukm5-test-kso-integration-decision.md` | Обновлён: DS integration теперь secondary; portrait player — primary |

### Добавленные blockers

```
ID:     P0-4 (обновлён)
Название: Landscape player несовместим с fleet 768×1024 portrait
Описание: Вся сеть использует КСО 768×1024 портрет с УКМ5 fullscreen kiosk.
         Landscape split 1920 player (ad zone 1440×1080) не является целевым для v1.
Решение: Portrait overlay/profile player для 768×1024

ID:     P0-5 (новый)
Название: Portrait player profile не спроектирован
Описание: v1 target = portrait 768×1024 player. Требуется дизайн:
         безопасные зоны, idle/busy detection, kill-switch, overlay/widget механика.
Решение: 38.0.4 Safe Zone Mapping → 38.0.5 Player profile design
```

---

## 9. Статус неизменных компонентов

| Компонент | Статус | Тесты | Примечание |
|---|---|---|---|
| Backend | ✅ Готов | 169/169 | Без изменений |
| Portal-web | ✅ Готов | 407/407 | Без изменений |
| State adapter | ✅ Готов | 86/86 | Требует UKM5 source (не геометрия) |
| Sidecar | ✅ Готов | 1838/1838 | API-контракт без изменений |
| Infra (bootstrap, preflight, systemd) | ✅ Готов | 227/227 | Player unit обновится под portrait |
| Landscape player | 📦 Архив | 968/968 | Сохранён для ландшафтных КСО в будущем |
| Portrait player | 🔴 Не начат | — | 38.0.4 → 38.0.5+ |

---

## 10. Roadmap после pivot

```
38.0.3-pivot (текущий)
  └── Зафиксировать portrait architecture ✅

38.0.4 — Safe Zone Mapping ✅ (done)
  ├── VNC screenshot экрана УКМ5 (read-only)
  ├── Определить критические UI-зоны
  ├── Предложить 2–3 варианта рекламной зоны
  └── Рекомендована Zone C: Product Grid y=400-640, 768×240

38.0.5 — Portrait Player Profile Design ✅ (done)
  ├── Выбрать механизм: overlay / idle-screensaver / widget
  ├── Спроектировать геометрию под 768×1024
  ├── Определить idle/busy detection без чековых данных
  └── Profile: portrait_idle_overlay_768, overlay y=400-640

38.0.6+ — Portrait Player Implementation
  ├── 38.0.6 ✅ Contract & Tests (71 тест)
  ├── 38.0.7 ✅ Shell Plan Support (59 тестов)
  ├── 38.0.8 ✅ Local Kill-Switch (41 тест)
  ├── 38.0.9 ✅ State Observer Stub (114 тестов)
  ├── 38.0.10 ⬜ Local smoke (Xvfb)
  └── 38.0.11 ⬜ Manual test on test KSO
```

---

## Файлы

- `docs/audit/kso-portrait-architecture-pivot.md` — этот документ
- `docs/audit/ukm5-test-kso-integration-decision.md` — integration decision (обновлён)
- `docs/audit/test-kso-end-to-end-readiness-gate.md` — readiness gate (обновлён)
- `docs/audit/test-kso-deployment-dry-run.md` — dry run (обновлён)
- `docs/audit/technical-debt-register.md` — реестр техдолга (обновлён)
- `docs/audit/technical-debt-next-actions.md` — план действий (обновлён)
- `docs/audit/one-kso-pilot-readiness-plan.md` — план (обновлён)

## Журнал

### 2026-06-24 — Шаг 38.0.9

State observer реализован: `kso_player/state_observer.py` + shell plan интеграция + 114 тестов ✅.

### 2026-06-24 — Шаг 38.0.8

Kill-switch реализован: `kso_player/kill_switch.py` + интеграция с shell plan + 41 тест ✅.

### 2026-06-24 — Шаг 38.0.7

Shell plan реализован: `kso_player/shell_plan.py` + 59 тестов ✅.

### 2026-06-24 — Шаг 38.0.6

Profile contract реализован: `portrait_idle_overlay_768` + 71 тест ✅.

### 2026-06-24 — Шаг 38.0.5

Portrait player profile `portrait_idle_overlay_768` спроектирован. Overlay zone y=400-640, 768×240.
См. `docs/audit/portrait-player-profile-design.md`.

### 2026-06-24 — Шаг 38.0.4

Safe Zone Mapping завершён. Рекомендована Zone C (Product Grid 768×240). См. `docs/audit/ukm5-ui-safe-zone-mapping.md`.

### 2026-06-23 — Шаг 38.0.3-pivot

User clarification: вся сеть использует КСО 768×1024 portrait + УКМ5 fullscreen kiosk.
Старая гипотеза 1920×1080 landscape неверна для v1.

Принято решение:
- Landscape split player — снят как v1 target (сохранён для будущих ландшафтных КСО)
- v1 target = portrait 768×1024 UKM5-compatible player profile
- Backend/portal/sidecar/state-adapter/manifest/PoP — без изменений
- Меняется только исполнительный слой показа

Код не менялся. КСО не менялась. Документация обновлена.
