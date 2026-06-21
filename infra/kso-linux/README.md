# KSO Linux Production Deployment — systemd Unit Templates

**Статус:** 🐧 Templates only — installer будет позже.

## Что это

Production-ready systemd unit templates для КСО-терминала на Linux:

| Сервис | Описание |
|---|---|
| `kso-sidecar.service` | Синхронизация manifest/media, отправка PoP |
| `kso-player.service` | Chromium kiosk — показ рекламы |

## Структура каталогов на КСО

```
/opt/verny/kso/                    # Исходники приложения (read-only)
├── kso_player/
├── kso_sidecar_agent/
└── player_shell/                   # Immutable shell source

/etc/verny/kso/                     # Конфигурация (read-only)
├── sidecar.env                     # Секреты sidecar (chmod 600)
└── player.env                      # Параметры player

/var/lib/verny/kso/                 # Runtime данные (read-write)
├── state/                          # UKM 4 state adapter output
├── manifest/                       # Локальный manifest
├── media/                          # Локальный media cache
├── pop/                            # Proof of Play
│   ├── pending/
│   └── sent/
└── runtime/                        # Runtime shell (мутабельная копия)
    └── player_shell/

/run/verny/kso/                     # Runtime health (tmpfs)
├── sidecar-health.json
└── player-health.json

/var/log/verny/kso/                 # Логи (read-write)
```

## systemd unit templates

### `kso-sidecar.service`

Периодически синхронизирует manifest/media с backend и отправляет PoP.

```ini
[Unit]
Description=KSO Sidecar Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/verny/kso/sidecar.env
ExecStart=/usr/bin/python3 -m kso_sidecar_agent.cli sidecar-daemon \
    --root /var/lib/verny/kso \
    --backend-url ${VERNY_KSO_BACKEND_URL} \
    --device-code ${VERNY_KSO_DEVICE_CODE} \
    --device-secret-env VERNY_KSO_DEVICE_SECRET \
    --health-file /run/verny/kso/sidecar-health.json
```

**Критично:** секрет передаётся только через имя env-переменной `VERNY_KSO_DEVICE_SECRET`, аргумент принимает ИМЯ переменной, а не значение.

### `kso-player.service`

Запускает Chromium в kiosk-режиме и показывает рекламу.

```ini
[Unit]
Description=KSO Player
After=kso-sidecar.service
Wants=kso-sidecar.service

[Service]
Type=simple
EnvironmentFile=/etc/verny/kso/player.env
ExecStart=/usr/bin/python3 -m kso_player.cli runtime-daemon \
    --root /var/lib/verny/kso \
    --source-shell-dir /opt/verny/kso/player_shell \
    --runtime-shell-dir /var/lib/verny/kso/runtime/player_shell \
    --chromium-bin ${VERNY_KSO_CHROMIUM_BIN} \
    --confirm-launch \
    --confirm-display-completed \
    --max-cycles -1 \
    --health-file /run/verny/kso/player-health.json
```

**Зависимости:** `Wants=kso-sidecar.service` (не `Requires`). Player может показывать уже загруженный local cache, даже если backend/sidecar временно недоступны.

**`--confirm-display-completed`:** Включён в production template. Player пишет completed PoP только после завершения duration и повторной проверки idle gate. При не-активном экране (state не idle) PoP не пишется.

### Environment files

**`/etc/verny/kso/sidecar.env`** (chmod 600):
```bash
VERNY_KSO_BACKEND_URL=https://backend.example
VERNY_KSO_DEVICE_CODE=CHANGE_ME
VERNY_KSO_DEVICE_SECRET=CHANGE...
```

**`/etc/verny/kso/player.env`** (chmod 600):
```bash
VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium
```

## Security hardening

Оба сервиса используют systemd hardening:

| Опция | Значение |
|---|---|
| `NoNewPrivileges` | true |
| `PrivateTmp` | true |
| `ProtectSystem` | full |
| `ProtectHome` | true |
| `ReadWritePaths` | `/var/lib/verny/kso` `/run/verny/kso` `/var/log/verny/kso` |
| `ReadOnlyPaths` | `/opt/verny/kso` `/etc/verny/kso` |
| `Restart` | always |
| `RestartSec` | 5 |

**Примечание для Chromium:** Некоторые hardening-опции (например, `ProtectKernelTunables`, `ProtectClock`) не добавлены — они могут сломать Chromium на определённых конфигурациях GPU. Эти опции будут проверены при интеграционном тестировании на реальном КСО.

## Порядок установки (checklist)

1. **Создать пользователя и группу:**
   ```
   groupadd verny
   useradd -r -s /sbin/nologin -g verny -d /var/lib/verny verny
   ```

2. **Создать каталоги:**
   ```
   mkdir -p /opt/verny/kso /etc/verny/kso /var/lib/verny/kso /run/verny/kso /var/log/verny/kso
   ```

3. **Скопировать приложение:**
   ```
   cp -r apps/kso_player /opt/verny/kso/
   cp -r apps/kso_sidecar_agent /opt/verny/kso/
   cp -r apps/kso_player/player_shell /opt/verny/kso/
   ```

4. **Скопировать env файлы** (заполнить реальные значения):
   ```
   cp env-examples/kso-sidecar.env.example /etc/verny/kso/sidecar.env
   cp env-examples/kso-player.env.example /etc/verny/kso/player.env
   chmod 600 /etc/verny/kso/*.env
   chown root:verny /etc/verny/kso/*.env
   ```

5. **Скопировать systemd units:**
   ```
   cp systemd/kso-sidecar.service /etc/systemd/system/
   cp systemd/kso-player.service /etc/systemd/system/
   ```

6. **Установить права:**
   ```
   chown -R verny:verny /var/lib/verny/kso /run/verny/kso /var/log/verny/kso
   chown -R root:verny /opt/verny/kso /etc/verny/kso
   ```

7. **Проверить unit syntax:**
   ```
   systemd-analyze verify kso-sidecar.service
   systemd-analyze verify kso-player.service
   ```

8. **Reload systemd:**
   ```
   systemctl daemon-reload
   ```

9. **Запустить сервисы** (после проверки на тестовом стенде):
   ```
   # Сначала sidecar:
   systemctl enable --now kso-sidecar.service

   # Затем player:
   systemctl enable --now kso-player.service
   ```

## Мониторинг

**Health файлы:**
```
cat /run/verny/kso/sidecar-health.json | python3 -m json.tool
cat /run/verny/kso/player-health.json | python3 -m json.tool
```

**Статус сервисов:**
```
systemctl status kso-sidecar.service
systemctl status kso-player.service
```

**Логи:**
```
journalctl -u kso-sidecar.service -f
journalctl -u kso-player.service -f
```

## Что НЕ входит в v1

- Android TV
- LED-шелфбаннеры
- Электронные ценники (ESL)
- Price checker
- Мобильное приложение как рекламный канал

## Safe bootstrap script

Вместо ручного копирования используйте `install/kso_linux_bootstrap.py`.

### Dry-run (безопасно, без изменений)

```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --dry-run
```

### Staging target-root

```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --apply \
    --target-root /tmp/kso-install-root
```

Создаст полное дерево каталогов и скопирует unit/env файлы под `/tmp/kso-install-root`.

### Production (требует явного подтверждения)

```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --apply \
    --target-root / \
    --i-understand-this-writes-to-system-paths
```

**Что делает bootstrap:**
- Создаёт каталоги (`/opt/verny/kso`, `/etc/verny/kso`, ...)
- Копирует systemd unit templates в `/etc/systemd/system/`
- Копирует env examples как `.example` (не перезаписывает реальные `.env`)
- Проверяет env на `CHANGE_ME` placeholders (`--validate-env`)
- Проверяет unit syntax (`--verify-units`)

**Что НЕ делает bootstrap:**
- ❌ systemctl start / enable / restart / daemon-reload
- ❌ Не перезаписывает существующие env файлы
- ❌ Не перезаписывает существующие unit файлы
- ❌ Не запускает Chromium / player / sidecar

### Проверка unit syntax

```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --apply \
    --target-root /tmp/kso-install-root --verify-units
```

### Проверка env на placeholders

```bash
python3 infra/kso-linux/install/kso_linux_bootstrap.py --apply \
    --target-root /tmp/kso-install-root \
    --validate-env /etc/verny/kso/sidecar.env.example
```

## Preflight validator

После bootstrap используйте `preflight/kso_linux_preflight.py` для проверки готовности.

```bash
# Staging:
python3 infra/kso-linux/preflight/kso_linux_preflight.py \
    --target-root /tmp/kso-install-root

# Production (readonly):
python3 infra/kso-linux/preflight/kso_linux_preflight.py --target-root /

# С проверкой unit syntax и CLI:
python3 infra/kso-linux/preflight/kso_linux_preflight.py \
    --target-root / --verify-units --verify-cli
```

**Что проверяет preflight:**

| Категория | Что проверяется |
|---|---|
| Каталоги | 6 контрактных директорий, writable для var_lib/run/log |
| Systemd units | Наличие kso-sidecar.service + kso-player.service |
| Env files | Наличие, placeholders, required keys, HTTPS |
| Chromium | Настроен ли VERNY_KSO_CHROMIUM_BIN |
| Player shell | 5 required files в player_shell/ |
| Health path | Writable /run/verny/kso |
| CLI | sidecar-daemon --help, runtime-daemon --help |

**Preflight НИКОГДА:**
- ❌ Не меняет файлы
- ❌ Не запускает сервисы
- ❌ Не печатает значения секретов/токенов/URL

**Порядок:** bootstrap готовит структуру → preflight проверяет → ручной запуск сервисов.

## Что будет позже

- `install.sh` — установочный скрипт
- `Makefile` / `ansible` — автоматизация
- Интеграционные тесты на реальном КСО
- Тонкая настройка Chromium kiosk-флагов
