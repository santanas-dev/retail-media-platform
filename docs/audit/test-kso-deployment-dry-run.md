# Test KSO Deployment Dry Run Checklist

> **Статус:** ✅ Dry Run Verified (37.13)
>
> Дата: 2026-06-16
> Ревизия: 2 (37.15 — isolated test KSO risk acceptance)
>
> **Назначение:** Проверить готовность проекта к установке на реальную test KSO перед выездом.
> **НЕ:** установка на железо, pilot rollout, изменение кода.
>
> **Risk acceptance (37.15):** Physical test KSO в изолированном контуре.
> TEST_ONLY endpoint'ы без аутентификации временно приняты. Device auth добавляется перед pilot rollout.

---

## Что проверено

### Deployment Artifacts Inventory

| # | Артефакт | Путь | Статус | Тесты |
|---|---|---|---|---|
| 1 | Bootstrap installer | `infra/kso-linux/install/kso_linux_bootstrap.py` | ✅ 445 строк, dry-run по умолчанию | 23/23 |
| 2 | Preflight validator | `infra/kso-linux/preflight/kso_linux_preflight.py` | ✅ 708 строк, read-only | 29/29 |
| 3 | Release package builder | `infra/kso-linux/release/kso_release_package_builder.py` | ✅ 410 строк, dry-run по умолчанию | 28/28 |
| 4 | UKM4 state discovery | `infra/kso-linux/discovery/ukm4_state_discovery.py` | ✅ dry-run по умолчанию | 14/14 |

### Systemd Units

| # | Сервис | Путь | Статус | Env example |
|---|---|---|---|---|
| 1 | kso-state-adapter | `infra/kso-linux/systemd/kso-state-adapter.service` | ✅ | `kso-state-adapter.env.example` |
| 2 | kso-sidecar | `infra/kso-linux/systemd/kso-sidecar.service` | ✅ | `kso-sidecar.env.example` |
| 3 | kso-player | `infra/kso-linux/systemd/kso-player.service` | ✅ | `kso-player.env.example` |

### Соответствие путей readiness gate

| Путь | В bootstrap | В preflight | В systemd | В readiness gate |
|---|---|---|---|---|
| `/opt/verny/kso/` | ✅ | ✅ | ✅ | ✅ |
| `/etc/verny/kso/` | ✅ | ✅ | ✅ (EnvironmentFile) | ✅ |
| `/var/lib/verny/kso/` | ✅ | ✅ | ✅ | ✅ |
| `/run/verny/kso/` | ✅ | ✅ | ✅ | ✅ |
| `/var/log/verny/kso/` | ✅ | ✅ | — | ✅ |

### Соответствие геометрии

| Параметр | В player | В readiness gate |
|---|---|---|
| Экран | 1920×1080 | ✅ |
| Ad zone (левая) | 1440×1080 | ✅ |

### Dry Run команды

| Компонент | Команда | Результат |
|---|---|---|
| Bootstrap | `python3 kso_linux_bootstrap.py --dry-run` | План установки, без изменений |
| Preflight | `python3 kso_linux_preflight.py --target-root /` | Read-only проверка |
| Release builder | `python3 kso_release_package_builder.py --dry-run` | Сбор файлов, без создания архива |
| UKM4 discovery | `python3 ukm4_state_discovery.py --dry-run` | Поиск UKM4 без модификации |

---

## Что готово

### ✅ Можно запустить перед выездом (на dev-машине)

```bash
# 1. Release package — dry run (собрать список файлов)
cd /home/cobalt/retail-media-platform/infra/kso-linux/release
python3 kso_release_package_builder.py --dry-run

# 2. Release package — реальная сборка
python3 kso_release_package_builder.py --build --version 0.1.0 \
    --output-dir /tmp/kso-release

# 3. Bootstrap — dry run (план установки)
cd /home/cobalt/retail-media-platform/infra/kso-linux/install
python3 kso_linux_bootstrap.py --dry-run

# 4. Preflight — staging check
cd /home/cobalt/retail-media-platform/infra/kso-linux/preflight
python3 kso_linux_preflight.py --target-root /tmp/kso-install-root

# 5. Full regression — все suites
cd /home/cobalt/retail-media-platform
python3 -m unittest discover -s backend/tests -v
python3 -m unittest discover -s apps/portal-web/tests -v
PYTHONPATH=apps/kso_state_adapter python3 -m unittest discover -s apps/kso_state_adapter/tests -v
PYTHONPATH=apps/kso_player python3 -m unittest discover -s apps/kso_player/tests -v
PYTHONPATH=apps/kso_sidecar_agent:apps/kso_player python3 -m unittest discover -s apps/kso_sidecar_agent/tests -v
python3 -m unittest discover -s infra/kso-linux/tests -v

# 6. Backend health
curl http://127.0.0.1:8001/health
```

### ✅ Команды на test KSO (после доставки пакета)

```bash
# 1. Распаковать release package
tar xzf kso-runtime-0.1.0.tar.gz -C /tmp/kso-install

# 2. Preflight — проверка целевой системы
cd /tmp/kso-install/infra/kso-linux/preflight
sudo python3 kso_linux_preflight.py --target-root /

# 3. Bootstrap — dry run (убедиться что план корректен)
cd /tmp/kso-install/infra/kso-linux/install
sudo python3 kso_linux_bootstrap.py --dry-run

# 4. Bootstrap — apply (реальная установка)
sudo python3 kso_linux_bootstrap.py --apply --target-root / \
    --i-understand-this-writes-to-system-paths

# 5. Разместить конфиги (заполнить реальные значения)
sudo cp sidecar.env /etc/verny/kso/sidecar.env
sudo chmod 600 /etc/verny/kso/sidecar.env
sudo cp player.env /etc/verny/kso/player.env
sudo cp state-adapter.env /etc/verny/kso/state-adapter.env

# 6. Preflight — повторная проверка после установки
sudo python3 kso_linux_preflight.py --target-root /

# 7. Запуск сервисов (только после заполнения конфигов!)
sudo systemctl daemon-reload
sudo systemctl start kso-state-adapter
sudo systemctl start kso-sidecar
sudo systemctl start kso-player

# 8. Проверить статус
systemctl status kso-state-adapter kso-sidecar kso-player

# 9. Проверить health
cat /run/verny/kso/sidecar-health.json
cat /run/verny/kso/player-health.json
```

---

## Env-параметры (без раскрытия секретов)

### `sidecar.env` — заполнить перед установкой

| Переменная | Описание | Откуда взять |
|---|---|---|
| `VERNY_KSO_BACKEND_URL` | URL backend API | Администратор сети |
| `VERNY_KSO_DEVICE_CODE` | Идентификатор КСО | Backend → `/api/devices/kso` |
| `VERNY_KSO_DEVICE_SECRET` | Device secret | Backend → device credential |
| `VERNY_KSO_MODE` | Режим работы | `test_kso` |

### `player.env` — заполнить перед установкой

| Переменная | Описание |
|---|---|
| `VERNY_KSO_PLAYER_MODE` | `test_kso` |
| `VERNY_KSO_PLAYER_SHELL_SNAPSHOT` | `/var/lib/verny/kso/runtime/shell_snapshot.html` |

### `state-adapter.env` — заполнить перед установкой

| Переменная | Описание |
|---|---|
| `VERNY_KSO_STATE_SOURCE` | `static` |
| `VERNY_KSO_STATIC_STATE` | `test_kso_active` |

---

## Проверки сети (на test KSO)

```bash
# 1. Доступность backend
curl -v http://<BACKEND_URL>/health
# Ожидание: {"status":"ok","db":"connected"}

# 2. Доступность manifest endpoint
curl -v http://<BACKEND_URL>/api/device-gateway/kso/<DEVICE_CODE>/manifest
# Ожидание: 200 + published manifest JSON (или 404 если ещё не опубликован)

# 3. Доступность PoP endpoint
curl -v -X POST http://<BACKEND_URL>/api/device-gateway/kso/<DEVICE_CODE>/pop \
  -H "Content-Type: application/json" \
  -d '{"event_code":"dry-run-test-001","media_ref":"media/current/slot-000","event_type":"impression"}'
# Ожидание: 404 device_not_found или 404 no_published_manifest (но НЕ connection refused/timeout)

# 4. Разрешение DNS
nslookup <BACKEND_HOSTNAME>
```

---

## Какие логи смотреть

| Лог | Путь | Что искать |
|---|---|---|
| Sidecar | `/var/log/verny/kso/sidecar.log` | `ERROR`, `Connection refused`, `401` |
| Player | `/var/log/verny/kso/player.log` | `ERROR`, `manifest not found` |
| State adapter | `/var/log/verny/kso/state-adapter.log` | `ERROR`, `source unavailable` |
| Systemd | `journalctl -u kso-sidecar -n 50` | OOM, segfault, exit code |
| Systemd | `journalctl -u kso-player -n 50` | Chromium crash |
| Systemd | `journalctl -u kso-state-adapter -n 50` | File permission errors |

---

## Что считается успехом dry run

| # | Критерий |
|---|---|
| ✅ | Все тесты green на dev-машине |
| ✅ | Release package собран без ошибок |
| ✅ | Bootstrap dry-run показывает корректный план |
| ✅ | Preflight проходит на `/tmp/kso-install-root` |
| ✅ | Backend `/health` → 200 |
| ✅ | Сетевые проверки на test KSO проходят (backend доступен) |
| ✅ | Все конфиги заполнены корректными значениями |
| ✅ | Сервисы запускаются без ошибок |
| ✅ | Health files содержат валидный JSON |

---

## Что блокирует реальную установку

| # | Блокер | Почему |
|---|---|---|
| 🛑 | Backend недоступен с test KSO | Сеть, firewall, DNS |
| 🛑 | Device credential не создан | Нельзя аутентифицировать sidecar |
| 🛑 | Manifest endpoint возвращает 5xx | Manifest generation сломан |
| 🛑 | PoP endpoint недоступен | PoP ingest не работает |
| 🛑 | Bootstrap apply падает | Права, дисковое пространство, зависимости |
| 🛑 | Preflight показывает ошибки | Система не готова |
| 🛑 | Сервисы не стартуют | Конфиги невалидны, пути не созданы |
| 🛑 | Нет sudo-прав | Нельзя установить systemd units |

---

## Checklist: готово / не готово

### Dev-машина (перед выездом)

| # | Проверка | Готово? |
|---|---|---|
| 1 | Все regression suites green | ☐ |
| 2 | Backend `/health` → 200 | ☐ |
| 3 | Release package собран | ☐ |
| 4 | Bootstrap dry-run успешен | ☐ |
| 5 | Preflight staging успешен | ☐ |
| 6 | Env-примеры заполнены (без реальных секретов) | ☐ |
| 7 | Документация актуальна | ☐ |
| 8 | Git clean, все изменения закоммичены | ☐ |

### Test KSO (на месте)

| # | Проверка | Готово? |
|---|---|---|
| 1 | Сетевой доступ до backend подтверждён | ☐ |
| 2 | Backend `/health` доступен | ☐ |
| 3 | Manifest endpoint доступен | ☐ |
| 4 | PoP endpoint доступен | ☐ |
| 5 | Права sudo есть | ☐ |
| 6 | Preflight проходит на `/` | ☐ |
| 7 | Bootstrap apply успешен | ☐ |
| 8 | Конфиги размещены (sidecar.env 600) | ☐ |
| 9 | Сервисы запущены | ☐ |
| 10 | Health files валидны | ☐ |
| 11 | Sidecar получил manifest | ☐ |
| 12 | Player сгенерировал shell snapshot | ☐ |
| 13 | PoP отправлен → backend | ☐ |
| 14 | PoP виден в портале | ☐ |

---

## Параметры для ручного получения перед установкой

| # | Параметр | Кто предоставляет | Формат |
|---|---|---|---|
| 1 | Backend URL | Администратор сети | `http://<host>:8001` или `https://...` |
| 2 | Device code | Backend admin | `demo_kso_001` (из seed) или новый |
| 3 | Device secret | Backend admin | Из device credential |
| 4 | Test KSO hostname/IP | Администратор сети | IP или hostname |
| 5 | Права sudo | Администратор системы | `sudo` доступ |
| 6 | Сетевой доступ | Администратор сети | Порт 8001 (или другой) открыт |

---

## Файлы

- `docs/audit/test-kso-deployment-dry-run.md` — этот документ
- `docs/audit/test-kso-end-to-end-readiness-gate.md` — readiness gate с E2E проверкой
- `docs/audit/one-kso-pilot-readiness-plan.md` — план test KSO → pilot rollout
- `infra/kso-linux/README.md` — KSO Linux deployment (systemd, пути, конфиги)
- `infra/kso-linux/install/kso_linux_bootstrap.py` — safe bootstrap installer
- `infra/kso-linux/preflight/kso_linux_preflight.py` — preflight validator
- `infra/kso-linux/release/kso_release_package_builder.py` — release package builder

## Обновления

### Шаг 37.13 — Test KSO Deployment Dry Run (2026-06-16)

Проверены все deployment артефакты:
- Bootstrap installer — ✅ 23/23 тестов
- Preflight validator — ✅ 29/29 тестов
- Systemd units × 3 — ✅ 73/73 тестов
- Release package builder — ✅ 28/28 тестов
- Env examples × 3 — ✅ без секретов
- Пути совпадают с readiness gate — ✅
- Геометрия 1920×1080 / 1440×1080 — ✅
- Dry run команды для всех компонентов — ✅
- Блокеров не найдено.
