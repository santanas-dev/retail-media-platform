# KSO Linux Pilot First-Start Runbook

> **Назначение:** безопасный первый ручной запуск трёх сервисов KSO
> на тестовом Linux КСО (СуперМаг УКМ 4, Chromium kiosk).
>
> **Для кого:** инженер, выполняющий первый запуск на тестовом оборудовании.
>
> **Статус:** 📋 Runbook — ручные команды. Не автоматизация.
>
> Последнее обновление: 2026-06-21

---

## Цель пилота

Подтвердить, что три сервиса KSO (`state-adapter`, `sidecar`, `player`)
запускаются, взаимодействуют и корректно реагируют на изменение состояния:
- `unknown` → player **hold** (реклама не показывается)
- `idle` (только для теста) → player **play** (реклама показывается)
- Возврат в `unknown` → player снова **hold**

Без реальной интеграции с УКМ 4. Без production-нагрузки.

---

## Что должно быть готово до начала

- [ ] Тестовый Linux КСО с установленным Chromium, Python 3.11+
- [ ] Код KSO скопирован на КСО (player, sidecar, state adapter, player_shell)
- [ ] Выполнен `bootstrap --dry-run` (план без изменений)
- [ ] Прочитан `infra/kso-linux/README.md`
- [ ] Прочитан `docs/kso/ukm4-state-source-discovery.md`
- [ ] Доступен `sudo` для команд `systemctl`
- [ ] Открыт терминал с правами на чтение `/run/verny/kso/` и `/var/lib/verny/kso/`

---

## Что запрещено

| Запрещено | Почему |
|---|---|
| `systemctl enable` | Автозапуск — только после успешного пилота |
| `systemctl restart` | Сначала понять причину → `stop` → `start` |
| Ставить `idle` как default | `unknown` — безопасный hold |
| Читать логи/БД/чеки УКМ 4 | ПДн, фискальные данные |
| Делать скриншоты с чеками/платежами | ПДн на скриншотах |
| Передавать секреты в командной строке | Утечка в историю/bash |
| Публиковать env values в отчёт | Секреты/токены |
| Менять конфигурацию УКМ 4 | Только read-only наблюдение |
| Менять сетевую схему КСО | Пилот на существующей сети |

---

## Файлы и каталоги

```
/opt/verny/kso/                    # Код приложения (read-only)
├── kso_player/
├── kso_sidecar_agent/
├── kso_state_adapter/
└── player_shell/                   # 5 файлов: index.html, styles.css,
    │                               #   player.js, bootstrap.js, bootstrap_snapshot.js

/etc/verny/kso/                     # Конфигурация
├── state-adapter.env               # chmod 600
├── sidecar.env                     # chmod 600
└── player.env                      # chmod 600

/var/lib/verny/kso/                 # Runtime данные
├── state/kso_state.json            # Пишет state adapter, читает player
├── manifest/                       # Локальный кеш manifest
├── media/                          # Локальный кеш media
├── pop/pending/                    # PoP-события до отправки
├── pop/sent/                       # Отправленные PoP
└── runtime/player_shell/           # Runtime копия shell

/run/verny/kso/                     # Health (tmpfs)
├── state-adapter-health.json
├── sidecar-health.json
├── player-health.json
└── ukm4-safe-state.json            # Опциональный safe status file

/var/log/verny/kso/                 # Логи

/etc/systemd/system/                # systemd units
├── kso-state-adapter.service
├── kso-sidecar.service
└── kso-player.service
```

---

## Шаг 1: Bootstrap dry-run

**Команда (read-only, безопасно):**
```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --dry-run
```

**Ожидаемый результат:** план директорий и файлов, `status: ok`, `applied: false`.

Если ошибка — не продолжать, пока не исправлена.

---

## Шаг 2: Bootstrap apply на тестовом КСО

**Команда (требует `sudo`, создаёт каталоги):**
```bash
sudo python3 infra/kso-linux/install/kso_linux_bootstrap.py --apply \
    --target-root / \
    --i-understand-this-writes-to-system-paths
```

**Ожидаемый результат:** `status: ok`, `applied: true`, созданы каталоги,
скопированы systemd unit files (3 шт.) и env examples (3 шт. `.example`).

**Проверка:**
```bash
ls -la /opt/verny/kso/ /etc/verny/kso/ /var/lib/verny/kso/ /run/verny/kso/ /var/log/verny/kso/
ls -la /etc/systemd/system/kso-*.service
```

---

## Шаг 3: Заполнение env файлов

Скопировать `.env.example` в `.env` и заполнить реальными значениями:

```bash
sudo cp /etc/verny/kso/state-adapter.env.example /etc/verny/kso/state-adapter.env
sudo cp /etc/verny/kso/sidecar.env.example /etc/verny/kso/sidecar.env
sudo cp /etc/verny/kso/player.env.example /etc/verny/kso/player.env
sudo chmod 600 /etc/verny/kso/*.env
sudo chown root:verny /etc/verny/kso/*.env
```

### Шаблоны (значения заменить на реальные)

**`/etc/verny/kso/state-adapter.env`:**
```bash
VERNY_KSO_STATE_SOURCE=static
VERNY_KSO_STATIC_STATE=unknown
VERNY_KSO_SOURCE_FILE=/run/verny/kso/ukm4-safe-state.json
```
> ⚠️ `unknown` — безопасный default. Player будет в hold.

**`/etc/verny/kso/sidecar.env`:**
```bash
VERNY_KSO_BACKEND_URL=https://backend.example
VERNY_KSO_DEVICE_CODE=CHANGE_ME
VERNY_KSO_DEVICE_SECRET=CHANGE_ME_SECRET
```
> ⚠️ `backend.example`, `CHANGE_ME`, `CHANGE_ME_SECRET` — заменить.
> **В отчёт реальные значения НЕ присылать.**

**`/etc/verny/kso/player.env`:**
```bash
VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium
```
> Проверить путь к Chromium: `which chromium`

---

## Шаг 4: Preflight

**Команда (read-only, безопасно):**
```bash
python3 infra/kso-linux/preflight/kso_linux_preflight.py --target-root /
```

**Ожидаемый результат:** `status: ok` или `status: warning` (env placeholders —
допустимо, если значения заполнены). `status: error` — не продолжать.

**С проверкой unit syntax и CLI (опционально, требует systemd):**
```bash
python3 infra/kso-linux/preflight/kso_linux_preflight.py \
    --target-root / --verify-units --verify-cli
```

> ⚠️ Preflight НЕ запускает сервисы, НЕ меняет файлы, НЕ печатает значения секретов.

---

## Шаг 5: systemd-analyze verify

**Команды:**
```bash
sudo systemd-analyze verify /etc/systemd/system/kso-state-adapter.service
sudo systemd-analyze verify /etc/systemd/system/kso-sidecar.service
sudo systemd-analyze verify /etc/systemd/system/kso-player.service
```

**Ожидаемый результат:** без ошибок для каждого юнита.

```bash
sudo systemctl daemon-reload
```

---

## Шаг 6: Первый запуск state-adapter (safe mode)

**Ручная команда:**
```bash
sudo systemctl start kso-state-adapter.service
```

**Проверка статуса:**
```bash
sudo systemctl status kso-state-adapter.service --no-pager
```

**Проверка health-файла:**
```bash
cat /run/verny/kso/state-adapter-health.json
```
> Ожидается: `"status":"running"`. Если нет — проверить `journalctl -u kso-state-adapter.service -n 20`.

**Проверка kso_state.json (должен быть `unknown`):**
```bash
cat /var/lib/verny/kso/state/kso_state.json
```
> Ожидается: `{"state":"unknown",...}`. State adapter пишет этот файл.
> **В отчёт raw JSON не присылать.** Подтвердить только `state=unknown`.

**Проверка fail-closed — прервать подачу source → adapter должен написать `unknown`:**
Адаптер в режиме `static unknown` уже fail-closed — всегда пишет `unknown`.
Для file source: удалить временно source file → adapter должен написать `error`.

---

## Шаг 7: Первый запуск sidecar

**Ручная команда:**
```bash
sudo systemctl start kso-sidecar.service
```

**Проверка статуса:**
```bash
sudo systemctl status kso-sidecar.service --no-pager
```

**Проверка manifest/media cache:**
```bash
ls /var/lib/verny/kso/manifest/ && echo "manifest OK" || echo "manifest MISSING"
ls /var/lib/verny/kso/media/ && echo "media OK" || echo "media MISSING"
```
> ⚠️ Если backend недоступен на тестовом КСО — manifest/media будут пусты.
> Это допустимо для пилота, если проверяется только локальный pipeline.

**Health:**
```bash
cat /run/verny/kso/sidecar-health.json
```
> Ожидается: `"status":"running"`.

---

## Шаг 8: Первый запуск player

**Ручная команда:**
```bash
sudo systemctl start kso-player.service
```

**Проверка статуса:**
```bash
sudo systemctl status kso-player.service --no-pager
```

**Health:**
```bash
cat /run/verny/kso/player-health.json
```
> Ожидается: `"status":"running"`.

---

## Шаг 9: Проверка hold при unknown

State adapter в `static unknown` → player должен быть в **hold**.

**Проверка:**
```bash
cat /var/lib/verny/kso/state/kso_state.json
```
> Должен быть `"state":"unknown"`.

Убедиться, что:
- Player НЕ запускает Chromium (или запускает, но не показывает рекламу)
- PoP-события НЕ пишутся (в pending пусто или только startup-маркеры)
- Player health показывает running, но idle_gate = false

**Проверка PoP pending:**
```bash
sudo find /var/lib/verny/kso/pop -maxdepth 2 -type f | wc -l
```
> Ожидается: 0 или минимальное число (startup-события без completed).
> **Не открывать raw event payload.** Только count.

---

## Шаг 10: Тестовый idle через safe source file

> ⚠️ **Только для тестового КСО.** Не production-режим.
> Это симулирует сигнал от УКМ 4 «терминал свободен».

### 10.1 Переключить state adapter на file source

```bash
sudo sed -i 's/^VERNY_KSO_STATE_SOURCE=.*/VERNY_KSO_STATE_SOURCE=file/' \
    /etc/verny/kso/state-adapter.env
```

Проверить:
```bash
grep VERNY_KSO_STATE_SOURCE /etc/verny/kso/state-adapter.env
# Должно быть: VERNY_KSO_STATE_SOURCE=file
```

### 10.2 Создать safe source file с idle

```bash
echo '{"state":"idle"}' | sudo tee /run/verny/kso/ukm4-safe-state.json >/dev/null
sudo chown verny:verny /run/verny/kso/ukm4-safe-state.json
```

### 10.3 Перезапустить state adapter с новым source

```bash
sudo systemctl stop kso-state-adapter.service
sudo systemctl start kso-state-adapter.service
```

### 10.4 Проверить kso_state.json = idle

```bash
cat /var/lib/verny/kso/state/kso_state.json
```
> Ожидается: `"state":"idle"`.

---

## Шаг 11: Проверка показа рекламы

После перехода в `idle` player должен начать показ.

**Проверка player health:**
```bash
cat /run/verny/kso/player-health.json
```
> Если idle_gate = true — player разрешил показ.

**Визуальная проверка на экране КСО:**
- Chromium запущен в kiosk-режиме
- Видна реклама (если manifest/media загружены) или player_shell placeholder

---

## Шаг 12: Проверка completed PoP

**Проверка pending (после одного completed):**
```bash
sudo find /var/lib/verny/kso/pop -maxdepth 2 -type f | wc -l
```
> **Не открывать raw event payload.** Только count.
> **Не выводить пути, ID, hash в отчёт.**

**Проверка отправки sidecar (после accepted):**
- Sidecar должен забрать completed PoP из pending
- После успешного accepted send — pending уменьшается, sent увеличивается

```bash
# Count pending
sudo find /var/lib/verny/kso/pop/pending -type f 2>/dev/null | wc -l

# Count sent
sudo find /var/lib/verny/kso/pop/sent -type f 2>/dev/null | wc -l
```
> **Не печатать raw file content. Не печатать имена файлов.**

---

## Шаг 13: Возврат в unknown (hold)

### 13.1 Вернуть source file в unknown

```bash
echo '{"state":"unknown"}' | sudo tee /run/verny/kso/ukm4-safe-state.json >/dev/null
```

### 13.2 Проверить kso_state.json

```bash
cat /var/lib/verny/kso/state/kso_state.json
```
> Ожидается: `"state":"unknown"`.

Player должен прекратить показ рекламы (hold).

---

## Rollback

### Безопасный порядок остановки

```bash
# 1. Сначала player
sudo systemctl stop kso-player.service

# 2. Затем sidecar
sudo systemctl stop kso-sidecar.service

# 3. Последним state adapter
sudo systemctl stop kso-state-adapter.service
```

### Проверка остановки

```bash
sudo systemctl status kso-player.service --no-pager
sudo systemctl status kso-sidecar.service --no-pager
sudo systemctl status kso-state-adapter.service --no-pager
```
> Все три должны быть `inactive (dead)`.

### Возврат safe defaults

```bash
# Вернуть state adapter на static unknown
sudo sed -i 's/^VERNY_KSO_STATE_SOURCE=.*/VERNY_KSO_STATE_SOURCE=static/' \
    /etc/verny/kso/state-adapter.env

# Удалить тестовый idle source file
sudo rm -f /run/verny/kso/ukm4-safe-state.json

# Или записать unknown (более безопасно)
echo '{"state":"unknown"}' | sudo tee /run/verny/kso/ukm4-safe-state.json >/dev/null
```

### Что НЕ удалять без approval

- **Sent PoP** — не удалять. Это audit trail.
- **Media cache** — не удалять без необходимости (долгая перезагрузка).
- **Env файлы** — не удалять. Только менять значения.
- **State adapter state/каталог** — адаптер сам управляет.

---

## Критерии успешного пилота

- [ ] Все три сервиса запускаются через `systemctl start`
- [ ] State adapter пишет `kso_state.json` со статусом `unknown` (safe default)
- [ ] State adapter переключается на `file` source и читает `{"state":"idle"}`
- [ ] Player в hold при `unknown` (реклама не показывается)
- [ ] Player показывает рекламу при `idle` (после тестового переключения)
- [ ] Player возвращается в hold при возврате `unknown`
- [ ] Sidecar синхронизирует manifest/media (если backend доступен)
- [ ] Sidecar отправляет PoP после accepted (если backend доступен)
- [ ] Rollback проходит чисто — все три сервиса останавливаются
- [ ] После возврата safe defaults система в исходном состоянии

---

## Что собрать в отчёт

### Разрешено включить

- Статус каждого сервиса (`systemctl status --no-pager` — **без** CGroup/process tree)
- Health-файлы (проверить на отсутствие секретов перед отправкой)
- `state=unknown` / `state=idle` (без raw JSON с `updated_at_utc` если там реальное время)
- Количество файлов в pending/sent (count только, без имён)
- Сообщения об ошибках из `journalctl -u <service> -n 20` (проверить на отсутствие секретов/токенов)
- Факты: «player запустился», «player в hold», «player показал рекламу»

### Запрещено включать

- ❌ Значения env переменных (секреты, токены, URL)
- ❌ Raw JSON из health-файлов (если есть поля кроме `status`)
- ❌ Raw JSON из kso_state.json (кроме поля `state`)
- ❌ Raw PoP event payload (ID, hash, paths, filenames)
- ❌ Имена файлов manifest/media
- ❌ Командную строку с аргументами (кроме стандартных из документации)
- ❌ Скриншоты с чеками/платежами/ПДн
- ❌ Логи УКМ 4
- ❌ Любые персональные или фискальные данные

---

## Ссылки

- `infra/kso-linux/README.md` — Deployment guide
- `docs/kso/ukm4-state-source-discovery.md` — UKM 4 State Source Discovery
- `apps/kso_state_adapter/README.md` — State Adapter docs
- `apps/kso_player/README.md` — Player docs
- `apps/kso_sidecar_agent/README.md` — Sidecar docs
