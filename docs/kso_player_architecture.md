# Mini-Design: Шаг 24 — KSO Player / Adapter Architecture

**Статус:** ⏳ На утверждении. Код не пишем, backend не меняем.

---

## 1. Goal

Спроектировать архитектуру будущего КСО-плеера / КСО-адаптера, который работает с уже готовым backend (11 device-facing endpoint'ов, runtime config, manifest delivery, media delivery, PoP, health & alerts, campaign reporting). Определить, что можно спроектировать сейчас, а что требует ответов от поставщика КСО ПО.

**Что НЕ делаем:**
- ❌ Код плеера/адаптера
- ❌ Android player
- ❌ Новые backend endpoint'ы
- ❌ Миграции
- ❌ Frontend
- ❌ Installer / auto-update
- ❌ Управление кассой / вмешательство в оплату
- ❌ Remote commands / push

---

## 2. Environment Assumptions (Что мы НЕ знаем)

На момент проектирования неизвестны:

| # | Вопрос | Почему важно |
|---|---|---|
| 1 | ОС КСО (Windows? Linux? Android? Embedded?) | Определяет язык, runtime, механизмы хранения |
| 2 | Есть ли браузерный слой (WebView, Electron, CEF)? | Варианты B/D зависят от этого |
| 3 | Можно ли ставить отдельный сервис (sidecar)? | Варианты A/D требуют прав установки |
| 4 | Есть ли API КСО-софта для получения состояния? | Без API нельзя узнать idle/payment/error/service mode |
| 5 | Можно ли делать overlay поверх КСО UI? | Варианты A/B с UI зависят от этого |
| 6 | Кто поставщик КСО ПО? | Риски сертификации, модель обновлений, SLA |
| 7 | Лимиты CPU/RAM/disk на КСО-терминале? | Определяет feasibility media-кэша и плеера |
| 8 | Можно ли хранить локальный кэш на диске КСО? | Без этого offline-режим невозможен |
| 9 | Какие права установки (admin? restricted user? kiosk?)? | Влияет на деплой и безопасность |
| 10 | Механизм обновления КСО-софта? | Нужно ли встраиваться в их pipeline |

**→ См. раздел 11 — полный список вопросов поставщику.**

---

## 3. Architecture Variants

### Вариант A — KSO Player как отдельный локальный сервис + overlay

**Описание:** На КСО-терминале запускается отдельный процесс/сервис (нативный или Python/Go), который:
- Имеет собственное окно/overlay поверх КСО UI
- Показывает рекламу (изображения, видео) в overlay-окне
- Сам управляет всеми циклами (auth, config, manifest, media, PoP)
- Имеет локальный media-кэш и PoP-очередь

| Аспект | Оценка |
|---|---|
| **Плюсы** | Полный контроль над воспроизведением. Не зависит от КСО UI-технологий. Можно реализовать сложные креативы. |
| **Минусы** | Overlay может мешать КСО UI. Нужны права на установку сервиса. Сложнее сертификация кассового ПО. |
| **Риски ИБ** | Overlay может перехватывать ввод (нужна жёсткая изоляция). Процесс с правами на overlay — привлекательная цель. |
| **Риски для кассового процесса** | Overlay может блокировать критичные элементы UI. При ошибке рендеринга — белый/чёрный экран поверх КСО. |
| **Сложность внедрения** | Высокая. Нужен деплой, мониторинг, обновление отдельного сервиса. |
| **Нужно от поставщика** | Разрешение на overlay, права на установку сервиса, гарантии неперекрытия критичных зон. |

### Вариант B — KSO Player как embedded WebView / browser component

**Описание:** КСО-софт предоставляет WebView/браузерный компонент (или SDK), в который загружается web-плеер. Плеер — HTML/JS, общается с backend через HTTP (JWT). Media — image/video в `<img>`/`<video>`.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Кроссплатформенность. Не нужен отдельный сервис. Проще деплой (URL или локальный bundle). |
| **Минусы** | Зависит от наличия WebView в КСО. Нет доступа к файловой системе (media-кэш ограничен). Нет secure storage для device_secret. |
| **Риски ИБ** | WebView — большой attack surface. XSS в плеере может скомпрометировать КСО. device_secret в JS-памяти. |
| **Риски для кассового процесса** | Браузерный рендеринг может забирать CPU. Труднее гарантировать fail_silent при ошибке JS. |
| **Сложность внедрения** | Средняя. Если WebView есть — быстро. Если нет — провал. |
| **Нужно от поставщика** | Есть ли WebView? Какая версия? Какие API доступны? Можно ли хранить данные локально? |

### Вариант C — KSO Adapter без UI, отдаёт manifest/media в КСО ПО

**Описание:** Adapter — лёгкий сервис без UI. Он получает manifest/media от backend и передаёт их в КСО ПО через API/Callback. КСО ПО само отвечает за отображение рекламы в своих зонах (idle screen, баннеры). Adapter только sync + PoP.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Минимальное вмешательство в КСО. Нет overlay-рисков. КСО ПО контролирует render. |
| **Минусы** | Зависит от API КСО-софта (может не быть). КСО ПО может неправильно отображать медиа. PoP-события нужно получать от КСО ПО. |
| **Риски ИБ** | Adapter не имеет доступа к UI → безопаснее. Но integration surface с КСО ПО — риск. |
| **Риски для кассового процесса** | Минимальны — adapter не трогает UI. КСО ПО само решает когда показывать. |
| **Сложность внедрения** | Зависит от API КСО. Если API нет — невозможно. |
| **Нужно от поставщика** | API для передачи media, API для получения PoP-событий, idle-триггеры, зоны показа. |

### Вариант D — Lightweight Sidecar Agent (рекомендуемый)

**Описание:** Минимальный нативный агент (Python/Go, ~20-50 MB), который:
- Синхронизирует manifest и media в локальный кэш
- Отправляет heartbeat, config refresh, PoP
- НЕ имеет собственного UI
- НЕ делает overlay
- Отдаёт готовые media-файлы + метаданные КСО ПО через локальный файловый API или HTTP (localhost)
- КСО ПО само забирает файлы и показывает их на idle screen

**Это Вариант C + упрощённый транспорт (файлы вместо API).**

| Аспект | Оценка |
|---|---|
| **Плюсы** | Максимальная безопасность. Нет overlay. Нет вмешательства в UI. Минимальный attack surface. Простая реализация. |
| **Минусы** | КСО ПО должно уметь показывать image/video из локальной папки. PoP-события нужно как-то получать (через файловый лог КСО ПО?) |
| **Риски ИБ** | Минимальные — agent outbound-only, без UI-доступа. Локальный HTTP на localhost — нужен контроль. |
| **Риски для кассового процесса** | Практически отсутствуют. Agent тихо работает в фоне, не трогает UI. |
| **Сложность внедрения** | Низкая. Нужен доступ к файловой системе и права на запуск фонового процесса. |
| **Нужно от поставщика** | Можно ли запустить фоновый процесс? Можно ли КСО ПО читать медиа из папки? Как получать idle-сигналы и PoP-события? |

---

## 4. Recommendation

**Рекомендуемый вариант: D — Lightweight Sidecar Agent.**

### Обоснование

1. **Безопасность прежде всего.** КСО — кассовое оборудование. Любое вмешательство в UI / overlay / рендеринг создаёт неприемлемые риски для кассового процесса. Sidecar agent работает в фоне, не трогает UI.

2. **Fail-safe by design.** Если agent упал — КСО продолжает работать. Если backend недоступен — agent тихо ждёт. Если manifest истёк — agent останавливает синхронизацию. Никакого влияния на оплату.

3. **Минимальные требования к КСО ПО.** Нужно только: (а) читать файлы из папки, (б) показывать image/video на idle screen, (в) сообщать о начале/конце показа (через файл или HTTP). Это базовые возможности любого современного КСО-софта.

4. **Простая реализация.** Агент легко написать на Python (aiohttp + aiofiles) или Go. Не нужен рендеринг, не нужен UI, не нужен браузер.

5. **Регуляторные риски минимальны.** Агент не влияет на кассовый сценарий → меньше проблем с сертификацией кассового ПО.

6. **Эволюция в Вариант C.** Если позже КСО ПО предоставит API — agent легко апгрейдить до полноценного adapter.

### Что agent НЕ делает (ограничения первой версии)

- Не показывает рекламу сам
- Не делает overlay
- Не имеет inbound портов (только локальный файловый API)
- Не выполняет remote commands
- Не обновляет себя автоматически
- Не собирает данные покупателя

---

## 5. Sidecar Agent — Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     KSO TERMINAL                                 │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │   KSO ПО     │    │        SIDECAR AGENT                  │   │
│  │              │    │                                       │   │
│  │  ┌────────┐  │    │  ┌─────────┐  ┌──────────┐           │   │
│  │  │Idle    │  │    │  │Auth     │  │Config    │           │   │
│  │  │Screen  │◄─┼────┼──┤Manager  │  │Manager   │           │   │
│  │  │(читает │  │    │  └────┬────┘  └────┬─────┘           │   │
│  │  │ media  │  │    │       │            │                  │   │
│  │  │ из     │  │    │  ┌────┴────────────┴──────┐           │   │
│  │  │ кэша)  │  │    │  │     MAIN LOOP           │          │   │
│  │  └────────┘  │    │  │  (asyncio scheduler)     │          │   │
│  │              │    │  └──┬───┬───┬───┬───┬──────┘           │   │
│  │  ┌────────┐  │    │     │   │   │   │   │                   │   │
│  │  │PoP Log │──┼────┼─────┘   │   │   │   │                   │   │
│  │  │(пишет  │  │    │  ┌──────┘   │   │   └──────────┐       │   │
│  │  │события)│  │    │  │  ┌───────┘   └───────┐      │       │   │
│  │  └────────┘  │    │  │  │                   │      │       │   │
│  │              │    │  ▼  ▼                   ▼      ▼       │   │
│  │              │    │ ┌──────────┐ ┌──────┐ ┌──────┐ ┌─────┐│   │
│  │              │    │ │Manifest  │ │Media │ │PoP   │ │Heart││   │
│  │              │    │ │Sync      │ │Cache │ │Queue │ │beat ││   │
│  │              │    │ └──────────┘ └──────┘ └──────┘ └─────┘│   │
│  └──────────────┘    │                                       │   │
│                       │  ┌─────────────────────────────────┐ │   │
│                       │  │     LOCAL STORAGE               │ │   │
│                       │  │  config/ manifest/ media/       │ │   │
│                       │  │  pop_queue/ state/ logs/        │ │   │
│                       │  └─────────────────────────────────┘ │   │
│                       │                                       │   │
│                       │         HTTPS (TLS 1.2+)              │   │
│                       └──────────────┬────────────────────────┘   │
│                                      │                            │
└──────────────────────────────────────┼────────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │    BACKEND      │
                              │  (уже готов)    │
                              └─────────────────┘
```

### Компоненты

| Компонент | Назначение | Язык/Стек |
|---|---|---|
| **AuthManager** | Получение JWT, refresh, хранение в памяти | Python (aiohttp) / Go |
| **ConfigManager** | Загрузка config, ETag/304, парсинг kso_safety | —"— |
| **ManifestSync** | Загрузка manifest, сравнение hash, определение новых items | —"— |
| **MediaCache** | Скачивание media-файлов, проверка sha256, LRU-вытеснение | —"— + aiofiles |
| **PoPQueue** | Накопление PoP, batch-отправка, дедупликация по device_event_id | —"— |
| **Heartbeat** | Периодический heartbeat с OK/WARNING/ERROR | —"— |
| **MainLoop** | Оркестратор расписания (asyncio/event loop) | —"— |
| **LocalStorage** | Файловая структура (см. раздел 7) | aiofiles / os |
| **Diagnostics** | CPU, RAM, disk usage, ошибки (только если `diagnostics_enabled`) | psutil |

### Межкомпонентное взаимодействие с КСО ПО

```
КСО ПО                          SIDECAR AGENT
──────                          ─────────────
                                 │
1. КСО в idle                    │
   ├─ читает media/current/      │  (agent уже синхронизировал
   │  из общей папки             │   latest manifest + media)
   ├─ показывает image/video     │
   └─ пишет событие в pop.log    │
                                 │
2. Agent читает pop.log          │
   └─ парсит новые события       │
      └─ добавляет в PoPQueue    │
         └─ batch-отправка       │
                                 │
3. КСО выходит из idle           │
   └─ agent НЕ вмешивается       │
      (KSO ПО само управляет)    │
```

**Интерфейс с КСО ПО: общая папка**

```
/var/lib/kso-adapter/          # или другая (определит поставщик)
├── media/
│   └── current/               # ← КСО ПО читает отсюда
│       ├── 001_main.jpg       #   media item 1
│       ├── 002_promo.mp4      #   media item 2
│       └── manifest.json      #   текущий manifest (read-only для КСО)
├── pop/                       # ← КСО ПО пишет сюда
│   └── events.log             #   JSONL: по одному событию на строку
└── status/                    # ← agent пишет свой статус
    └── agent_status.json      #   КСО ПО может читать для мониторинга
```

---

## 6. Runtime Loops

Все интервалы берутся из runtime config (GET /config/current).

```
┌──────────────────────────────────────────────────────────────┐
│ COLD START                                                   │
│ ─────────                                                    │
│ 1. Читает device_code + device_secret из secure storage      │
│ 2. POST /auth/token → JWT                                    │
│ 3. GET /config/current → начальный config                    │
│ 4. Переходит к WARM LOOP                                     │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ WARM LOOPS (параллельные, каждый со своим интервалом)        │
│ ──────────                                                   │
│                                                              │
│ AUTH REFRESH (за 30 сек до exp JWT)                          │
│   └── POST /auth/token → новый JWT                           │
│                                                              │
│ HEARTBEAT (heartbeat_interval_sec, default 60s)              │
│   └── POST /heartbeat {status: ok|warning|error}             │
│                                                              │
│ CONFIG REFRESH (manifest_refresh_interval_sec, default 60s)  │
│   └── GET /config/current (ETag/304)                         │
│       └── обновить kso_safety, интервалы, лимиты             │
│                                                              │
│ MANIFEST REFRESH (manifest_refresh_interval_sec)             │
│   └── GET /manifest/current (hash/304)                       │
│       └── если новый manifest:                               │
│           ├── определить новые media items                   │
│           ├── для каждого:                                   │
│           │   ├── GET /media/{id}/metadata (проверить sha256) │
│           │   ├── если нет в кэше: GET /media/{id} (download)│
│           │   ├── проверить sha256 скачанного файла           │
│           │   ├── сохранить в media/current/                  │
│           │   └── POST /media/cache/report                   │
│           └── POST /manifest/{id}/apply                      │
│                                                              │
│ MEDIA CACHE SYNC (при изменении manifest)                    │
│   └── LRU-вытеснение при превышении media_cache_max_mb       │
│       └── удалить старые, обновить media/current/            │
│                                                              │
│ PoP FLUSH (pop_flush_interval_sec, default 300s)             │
│   └── читать pop/events.log → парсить новые события          │
│       └── отправить batch'ами по pop_batch_max_events        │
│           └── POST /pop/events/batch                         │
│               └── при успехе: удалить отправленные из лога   │
│                                                              │
│ DIAGNOSTICS (diagnostics_sample_interval_sec, default 300s)  │
│   └── если diagnostics_enabled:                              │
│       └── собирать CPU%, RAM MB, disk usage, error count     │
│           └── логировать локально (позже: отправлять в       │
│              backend когда появится diagnostics endpoint)    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ SHUTDOWN                                                     │
│ ────────                                                     │
│ 1. Остановить все loops                                      │
│ 2. Flush PoP: отправить всё из pop/events.log                │
│ 3. Сохранить state.json                                      │
│ 4. Выход                                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Local Storage Design

```
/var/lib/kso-adapter/              # Базовый путь (определит поставщик)
│
├── secure/                        # Права: 0700, владелец: kso-agent
│   └── device_secret              # Только device_secret (plain, не логировать)
│
├── config/                        # Кэш конфигурации
│   └── current.json               # Последний config + config_hash
│
├── manifest/                      # Кэш манифеста
│   ├── current.json               # Текущий manifest + manifest_hash
│   └── history/                   # История manifest (для отката, макс 5)
│       ├── <manifest_version_id_1>.json
│       └── <manifest_version_id_2>.json
│
├── media/                         # Медиа-кэш
│   ├── cache/                     # LRU-кэш всех скачанных media
│   │   ├── <manifest_item_id_1>.jpg
│   │   ├── <manifest_item_id_2>.mp4
│   │   └── .cache_index.json      # Индекс: {item_id: {sha256, size, last_access}}
│   └── current/                   # Текущий активный набор (симлинки в cache/)
│       ├── 001_main.jpg -> ../cache/<item_id>.jpg
│       ├── 002_promo.mp4 -> ../cache/<item_id>.mp4
│       └── manifest.json          # Краткий manifest для КСО ПО (только media-список)
│
├── pop/                           # PoP-очередь
│   ├── events.log                 # JSONL: неотправленные события
│   └── sent/                      # Отправленные (для аудита, ротация)
│       └── events.2026-06-18.log
│
├── state/                         # Состояние агента
│   ├── agent_status.json          # {status, uptime, last_heartbeat, last_config,...}
│   └── device_state.json          # {auth_state, session_id, last_manifest_id,...}
│
├── logs/                          # Логи агента (ротация)
│   ├── agent.log                  # Основной лог (без secrets!)
│   ├── agent.error.log            # Только ошибки
│   └── archive/                   # Ротированные логи
│
└── tmp/                           # Временные файлы (очищать при старте)
```

### Правила хранения

| Что | Где | Права | Примечание |
|---|---|---|---|
| `device_secret` | `secure/device_secret` | 0400 | Только чтение владельцем. Никогда не логировать. |
| JWT | **Только в памяти** | — | Никогда на диск. |
| Config | `config/current.json` | 0644 | Без secrets. |
| Manifest | `manifest/current.json` | 0644 | Без secrets. |
| Media | `media/cache/` | 0644 | Проверять sha256 после скачивания. |
| PoP queue | `pop/events.log` | 0600 | Не содержит персональных данных. |
| State | `state/` | 0644 | Без secrets. |
| Logs | `logs/` | 0640 | Маскировать device_secret и JWT. |

### Что НЕ хранить

- ❌ Customer data (имена, карты, чеки, фото/видео покупателя)
- ❌ Payment data (суммы, транзакции, авторизации)
- ❌ КСО-специфичные данные (цены, остатки, скидки)
- ❌ JWT на диске
- ❌ `local_path` / `file_path` в backend-запросах

---

## 8. Offline Mode

### Правила

| Ситуация | Действие |
|---|---|
| Backend доступен | Полный цикл (все loops активны) |
| Backend недоступен, `offline_mode_enabled=true` | Продолжать синхронизацию media/current/ для КСО ПО по последнему валидному manifest |
| Backend недоступен, `offline_mode_enabled=false` | Остановить все запросы к backend. Ждать восстановления. |
| Offline дольше `max_offline_duration_sec` | Остановить показ. Очистить `media/current/`. Ждать восстановления. |
| Manifest TTL истёк (`manifest_ttl_sec`) | Остановить показ. Очистить `media/current/`. |
| Восстановление связи | 1. Auth refresh. 2. Config refresh. 3. Manifest refresh. 4. Flush PoP queue. |

### Offline PoP Queue

```
СХЕМА РАБОТЫ:

1. КСО ПО пишет событие в pop/events.log (JSONL)
   {"device_event_id":"uuid","manifest_item_id":"uuid","played_at":"ISO8601","duration_ms":5000,"play_status":"completed"}

2. Agent читает events.log каждые pop_flush_interval_sec
   - парсит только строки после последнего обработанного offset
   - формирует batch'и по pop_batch_max_events
   - отправляет POST /pop/events/batch

3. При успешной отправке:
   - перемещает обработанные строки в pop/sent/events.YYYY-MM-DD.log
   - обновляет offset

4. При ошибке отправки:
   - события остаются в events.log
   - повторная попытка при следующем flush
   - дедупликация через device_event_id на backend

5. При переполнении очереди (> 10 000 событий):
   - FIFO: старые события теряются
   - логировать потерю
   - отправлять alert в heartbeat (status=warning)
```

---

## 9. KSO Safety Guards

### Принцип: fail-closed

**Реклама не должна мешать работе КСО.** При любой неопределённости — останавливаем всё, что может повлиять на кассовый процесс.

### Матрица состояний

| Состояние КСО | Показ media? | Heartbeat? | Config sync? | Manifest sync? | PoP flush? |
|---|---|---|---|---|---|
| **idle** | ✅ Да | ✅ Да | ✅ Да | ✅ Да | ✅ Да |
| **scanning** (покупатель сканирует) | ❌ Нет | ✅ Да | ✅ Да | ✅ Да | ✅ Да |
| **payment** (оплата) | ❌ Нет | ✅ Да | ✅ Да | ✅ Да | ✅ Да |
| **error_screen** | ❌ Нет | ✅ Да | ✅ Да | ✅ Да | ✅ Да |
| **service_mode** | ❌ Нет | ✅ Да | ❌ Нет (не менять config) | ❌ Нет (не менять манифест) | ✅ Да |
| **unknown** (не можем определить) | ❌ Нет | ✅ Да | ✅ Да | ✅ Да | ✅ Да |

### Обязательные проверки ПЕРЕД каждым циклом

```
ПЕРЕД ОБНОВЛЕНИЕМ media/current/:
├── KSO в idle?              → если нет → НЕ обновлять media/current/
├── stop_on_transaction?     → если активна транзакция → НЕ обновлять
├── stop_on_payment?         → если оплата → НЕ обновлять
├── stop_on_error_screen?    → если экран ошибки → НЕ обновлять
├── stop_on_service_mode?    → если service mode → НЕ обновлять
├── CPU > max_cpu_percent?   → пропустить цикл, логировать
├── RAM > max_memory_mb?     → очистить старый кэш, логировать
└── ВСЁ OK → выполнить цикл
```

### Поведение агента при нештатных ситуациях

| Ситуация | Действие |
|---|---|
| КСО вышел из idle во время скачивания media | Прервать скачивание. Не обновлять media/current/. |
| Backend недоступен, КСО в idle | Offline-режим (если разрешён). Иначе — очистить media/current/. |
| Ошибка проверки sha256 | Не использовать файл. POST cache/report status=invalid_hash. Удалить. Скачать заново. |
| Config содержит неизвестное значение | Использовать default. Логировать warning. |
| Manifest содержит неподдерживаемый MIME | Пропустить item. Логировать. |
| Локальный кэш повреждён | Очистить весь media/cache/. Скачать заново при следующем цикле. |
| Agent crash / kill -9 | При рестарте: прочитать state, провалидировать кэш, начать с холодного старта. |
| `fail_behavior=fail_closed` | При любой нефатальной ошибке — полностью остановить агент. |
| `fail_behavior=fail_silent` | При нефатальной ошибке — тихо остановить показ (очистить media/current/), но продолжать sync/heartbeat/PoP. |

---

## 10. Security Rules

### Device secret

```
- Хранить в secure/device_secret (права 0400)
- Keychain/Keystore — если доступен на ОС КСО
- Если нет secure storage → зашифрованный файл с ключом из переменной окружения
- Никогда не логировать
- Не передавать никуда кроме /auth/token
- Ротация: ручная (через админку backend)
```

### JWT

```
- Только в памяти (переменная, не файл)
- Short-lived (проверять exp перед каждым запросом)
- Refresh за 30 сек до exp
- При 401 → немедленный re-auth
- При 3x 401 подряд → остановка, логирование, alert в heartbeat
```

### TLS / Network

```
- TLS 1.2+ (отказ от 1.0/1.1)
- Certificate validation (no --insecure)
- Certificate pinning (опционально, для production)
- Outbound-only: agent → backend
- НИКАКИХ inbound портов на КСО (только localhost:0 для внутренней связи)
- Если локальный HTTP для КСО ПО — bind на 127.0.0.1 только
```

### Данные

```
- НИКОГДА: персональные данные, чеки, карты, фото/видео покупателя
- НИКОГДА: human-токены, advertiser-токены
- НИКОГДА: local_path / file_path в backend-запросах
- НИКОГДА: secrets в логах (маскировать device_secret и JWT)
- PoP-события: только device_event_id + manifest_item_id + played_at + duration_ms
```

### Обновление

```
- НЕТ auto-update в v1
- Обновление только через КСО-администратора / MDM
- Подписанный бинарный пакет
- Проверка подписи перед установкой
```

### Remote commands

```
- ❌ НЕТ remote shell
- ❌ НЕТ remote command execution
- ❌ НЕТ push-уведомлений (poll-only)
- Позже (v2): подписанные команды через config с audit trail
```

---

## 11. Backend Readiness

### Endpoints — все готовы ✅

Backend предоставляет 11 device-facing endpoint'ов (все реализованы в Шагах 1–22):

| # | Endpoint | Назначение для agent | Статус |
|---|---|---|---|
| 1 | `POST /auth/token` | Cold start, refresh JWT | ✅ |
| 2 | `POST /heartbeat` | Периодический heartbeat | ✅ |
| 3 | `GET /config/current` | Загрузка runtime config (ETag/304) | ✅ |
| 4 | `GET /manifest/current` | Текущий manifest (hash/304) | ✅ |
| 5 | `GET /manifest/{id}` | Manifest по ID (fallback) | ✅ |
| 6 | `GET /media/{id}/metadata` | Проверка sha256 перед download | ✅ |
| 7 | `GET /media/{id}` | Скачивание media (stream) | ✅ |
| 8 | `POST /manifest/{id}/apply` | Подтверждение применения manifest | ✅ |
| 9 | `POST /media/cache/report` | Отчёт о статусе кэша | ✅ |
| 10 | `POST /pop/events` | Отправка одного PoP-события | ✅ |
| 11 | `POST /pop/events/batch` | Batch-отправка PoP | ✅ |

### Runtime Config — все поля готовы ✅

После Шага 23.2 backend отдаёт полный config (19 ключей) включая:

- `kso_safety` (6 sub-ключей: `stop_on_service_mode`, `fail_behavior`, `screen_zone`, `max_overlay_area_percent`, `max_cpu_percent`, `max_memory_mb`)
- `max_offline_duration_sec`, `manifest_ttl_sec`, `diagnostics_enabled`, `diagnostics_sample_interval_sec`, `media_prefetch_enabled`, `media_prefetch_max_items`, `local_storage_reserved_mb`
- Все интервалы (`heartbeat_interval_sec`, `manifest_refresh_interval_sec`, `pop_flush_interval_sec`, etc.)

### Health & Alerts ✅

- Content sync health (5 problem types)
- Campaign delivery reporting (PoP fallback, delivery_status)
- Alerts evaluate без дублей

### Оставшиеся GAP'ы (не блокируют v1 agent)

| # | GAP | Влияние | Приоритет |
|---|---|---|---|
| 1 | Нет endpoint для diagnostics agent health | Agent логирует локально | Future |
| 2 | Нет push-уведомлений (poll-only manifest) | Agent проверяет manifest по таймеру — OK | Future |
| 3 | Нет API для получения состояния КСО | Agent будет получать через файл / локальный вызов | Зависит от КСО |

### Что backend HE требует от agent

- Backend не шлёт команды на КСО (нет push)
- Backend не требует от agent немедленной реакции (poll-based)
- Backend не хранит состояние КСО (только heartbeat + PoP)
- Backend не знает о КСО UI (только логические события)

---

## 12. Вопросы поставщику КСО ПО

### Обязательные (без ответов невозможно начать)

| # | Вопрос | Почему важно |
|---|---|---|
| 1 | Какая ОС на КСО-терминале? Версия? | Язык, runtime, механизмы хранения |
| 2 | Можно ли установить фоновый процесс (sidecar service)? | Базовое требование Вариантов A/D |
| 3 | Есть ли API для определения состояния КСО (idle, scanning, payment, error, service)? | Без этого нельзя гарантировать безопасность показа |
| 4 | Можно ли КСО ПО показывать image/video из указанной папки на idle screen? | Базовое требование Варианта D |
| 5 | Какие права у процесса? (root? admin? restricted user?) | Влияет на файловую структуру и безопасность |
| 6 | Есть ли лимиты CPU/RAM/disk для сторонних процессов? Какие? | Определяет feasibility media-кэша |

### Желательные (помогут выбрать точный вариант)

| # | Вопрос | Почему важно |
|---|---|---|
| 7 | Есть ли браузерный слой (WebView, Chromium Embedded Framework)? | Вариант B требует этого |
| 8 | Можно ли делать overlay поверх КСО UI? | Варианты A/B требуют этого |
| 9 | Можно ли хранить локальный кэш файлов (до N MB)? | Offline-режим и media-кэш |
| 10 | Есть ли secure storage (Keychain/Keystore/TPM)? | Безопасное хранение device_secret |
| 11 | Как КСО ПО обновляется? Можно ли встроить agent в pipeline обновлений? | Деплой и lifecycle |
| 12 | Как КСО ПО логирует события? Можно ли читать его логи? | PoP-события: agent должен знать когда был показ |
| 13 | Есть ли у КСО-софта API для передачи media и получения событий? | Вариант C требует этого |
| 14 | Какие форматы media поддерживаются КСО ПО? (JPEG, PNG, MP4, WebM?) | Определяет acceptable MIME-типы |

### Регуляторные / ИБ

| # | Вопрос | Почему важно |
|---|---|---|
| 15 | Нужна ли сертификация дополнительного ПО на КСО? Какая? | Регуляторные риски |
| 16 | Есть ли требования по изоляции стороннего ПО от кассового процесса? | Безопасность |
| 17 | Какой процесс отключения/отката при инциденте? | Эксплуатация |
| 18 | Кто отвечает за мониторинг КСО-терминала? | Разделение ответственности |

---

## 13. Что предлагаю на следующем шаге (после утверждения)

1. **Шаг 24.1 — Sidecar Agent: Project Skeleton**
   - Создать `players/kso-agent/` в репозитории
   - Базовая структура на Python: `pyproject.toml`, `src/`, `tests/`
   - CLI: `kso-agent --device-code X --device-secret Y --base-url Z`
   - Health-check: запуск → auth → heartbeat → graceful shutdown

2. **Шаг 24.2 — Config + Manifest Sync**
   - ConfigManager (ETag/304, парсинг kso_safety)
   - ManifestSync (hash/304, сравнение items)
   - Локальное хранение `config/current.json`, `manifest/current.json`

3. **Шаг 24.3 — Media Cache**
   - MediaCache: download, sha256, LRU-вытеснение
   - MediaSync: запись в `media/current/`, обновление `cache/report`

4. **Шаг 24.4 — PoP Queue + Heartbeat**
   - PoPQueue: чтение `pop/events.log`, batch-отправка
   - Heartbeat loop

5. **Шаг 24.5 — KSO Safety Integration**
   - Интеграция с API/файлом состояния КСО (когда станет известен)
   - Safety checks: idle, transaction, payment, error, service mode
   - CPU/RAM monitoring

6. **Шаг 24.6 — Offline Mode + Resilience**
   - Offline-очередь, дедупликация, TTL
   - Graceful degradation при ошибках сети

**Но все шаги после 24 зависят от ответов поставщика КСО (раздел 12). Без них пишем только skeleton (24.1) — остальное заглушки.**

---

## 14. Verification Plan (будущий шаг)

После реализации agent:

1. **Cold start:** agent стартует → auth 200 → config получен → manifest получен
2. **Media sync:** media скачан → sha256 совпадает → `media/current/` обновлён
3. **PoP:** КСО ПО пишет событие в pop.log → agent читает → batch отправлен → 200
4. **Heartbeat:** agent шлёт heartbeat каждые N сек → backend видит устройство онлайн
5. **Safety:** КСО выходит из idle → agent очищает media/current/ → показ остановлен
6. **Offline:** backend недоступен → agent работает по последнему manifest → PoP копится → при восстановлении отправлен
7. **Crash recovery:** `kill -9` → agent рестартует → восстанавливает состояние → продолжает
8. **Security:** device_secret в логах не найден → JWT на диске не найден → local_path в запросах не найден
9. **Campaign report:** PoP отображается в `actual_play_count` в campaign delivery reporting

---

## 15. Commit

Не делаем — только mini-design на утверждение.
