# Test KSO Sidecar Config — Controlled Phase B Application Preflight

> **Step:** 38.10  
> **Date:** 2026-06-26  
> **Status:** 📋 PREFLIGHT ONLY — no KSO access, no SSH, no sidecar execution  
> **ВАЖНО:** This document DESCRIBES the plan. It does NOT execute any actions on KSO.

---

## 1. Purpose

This document defines the **controlled procedure** for applying sidecar config to the test KSO device **when Phase B is approved for execution**. Until then, all commands are templates with placeholders — no real values.

---

## 2. Required Real Values (когда Phase B будет запущена)

| Input | Description | Пример формата | Откуда |
|---|---|---|---|
| `TEST_BACKEND_BASE_URL` | HTTPS URL Retail Media Backend API | `https://api.example.com` | Оператор знает / Admin panel |
| `TEST_KSO_DEVICE_CODE` | KSO device code (registered in backend) | `kso-0001-test` | Backend `/api/test-kso/seed` output |
| `DEVICE_SECRET` | Device authentication secret | 16–512 chars | Генерируется бэкендом при регистрации устройства |
| `AGENT_ROOT` | Absolute path to agent root on KSO | `/opt/kso-agent` | Оператор задаёт |

> ⚠️ **НИКОГДА не вводить значения в чат, docs, или git.** Только локально на КСО.

---

## 3. Who Does What

| Роль | Действие |
|---|---|
| **Оператор** | Копирует template → заполняет config → вводит secret → верифицирует |
| **Backend** | Предоставляет device_code + secret через admin UI (будущий шаг) |
| **Sidecar** | Читает config + secret локально; никакие значения не передаются наружу |
| **Hermes Agent** | Не участвует в физическом выполнении (только план + документация) |

---

## 4. Что куда пишется на КСО

| Файл на КСО | Содержимое | Защита |
|---|---|---|
| `<AGENT_ROOT>/config/agent_config.json` | `backend_base_url`, `device_code`, `tls_verify`, ... | `.gitignore`, не коммитить |
| `<AGENT_ROOT>/config/device_secret.dev` | `DEVICE_SECRET` | `.gitignore`, `chmod 0600`, stdin only |
| `<AGENT_ROOT>/agent_status.json` | Статус агента (создаётся `init-local-root`) | Автоматически |
| `<AGENT_ROOT>/state/`, `manifest/`, `media/`, `pop/`, `runtime_config/` | Пустые директории | `init-local-root` |

**Никуда больше не пишется:**
- ❌ Не в `/etc/`
- ❌ Не в `~/.ssh/`
- ❌ Не в системный crontab
- ❌ Не в git (`.gitignore` блокирует)

---

## 5. Operator Checklist (Phase B Controlled)

### 5.1 Pre-flight Safety Gates

Перед началом убедиться:

| # | Gate | Как проверить |
|---|---|---|
| G1 | Backend жив | `curl -k <TEST_BACKEND_BASE_URL>/health` → `{"status":"ok"}` |
| G2 | AGENT_ROOT не существует | `ls <AGENT_ROOT>` → `No such file or directory` |
| G3 | Git clean на dev-машине | `git status --short` → пусто |
| G4 | Шаблон скопирован | `agent_config.json.example` НЕ изменён (git diff пуст) |
| G5 | Никто не смотрит в консоль | Secret будет вводиться через stdin — убедиться, что stdout не пишется в лог |

### 5.2 Step-by-Step (КОМАНДЫ-ШАБЛОНЫ — без реальных значений)

#### Step 1: Init agent root

```bash
# На КСО:
sidecar init-local-root --root <AGENT_ROOT>
```

Ожидаемый вывод:
```
Initialized agent root at: <AGENT_ROOT>
```

#### Step 2: Copy config template (на dev-машине)

```bash
# На dev-машине (НЕ на КСО):
cp apps/kso_sidecar_agent/config/agent_config.json.example /tmp/agent_config_filled.json
```

#### Step 3: Fill config (на dev-машине, в редакторе)

```bash
# Открыть /tmp/agent_config_filled.json в редакторе:
# Заменить:
#   "<TEST_BACKEND_BASE_URL>" → реальный URL
#   "<TEST_KSO_DEVICE_CODE>"  → реальный device_code
# Сохранить.
# НЕ КОММИТИТЬ.
```

#### Step 4: Transfer config to KSO

```bash
# На КСО (скопировать заполненный файл):
# Поместить /tmp/agent_config_filled.json → <AGENT_ROOT>/config/agent_config.json
# Проверить: cat <AGENT_ROOT>/config/agent_config.json | python3 -m json.tool
```

> ⚠️ После проверки удалить `/tmp/agent_config_filled.json` с dev-машины:
> ```bash
> shred -u /tmp/agent_config_filled.json
> ```

#### Step 5: Write device secret (stdin only)

```bash
# На КСО:
# Секрет НЕ передаётся как аргумент — только через stdin!
echo -n '<DEVICE_SECRET_VALUE>' | sidecar secret-store-set \
  --root <AGENT_ROOT> \
  --dev-secret-store
```

Ожидаемый вывод: **ничего** (успех — отсутствие ошибки).

#### Step 6: Verify config (safe summary)

```bash
# На КСО:
sidecar config-status --root <AGENT_ROOT>
```

Ожидаемый вывод (пример):
```
present: True
ok: True
backend_scheme: https
backend_host: api.example.com
device_code: kso-0001-test
tls_verify: True
has_placeholders: False
placeholder_fields: []
```

> ✅ `backend_host` виден (hostname), полный URL — нет.
> ✅ `device_code` виден, но он не секрет.
> ✅ `has_placeholders: False` — все шаблоны заменены.

#### Step 7: Verify secret store (safe summary)

```bash
# На КСО:
sidecar secret-store-check --root <AGENT_ROOT> --dev-secret-store
```

Ожидаемый вывод:
```
present: True
mode: dev-only
permissions_ok: True
readable_by_agent: True
```

> ✅ Значение секрета НЕ выводится — только `present`/`permissions_ok`.

#### Step 8: Full doctor check

```bash
# На КСО:
sidecar doctor --root <AGENT_ROOT> --dev-secret-store
```

Ожидаемые ключевые поля:
```
folders_ok: True
agent_status_ok: True
config_ok: True
runtime_config_ok: False      # ожидаемо — не синхронизирован с backend
manifest_ok: False             # ожидаемо — не синхронизирован
media_cache_ok: True           # пустой кеш — ok
```

### 5.3 Stop Criteria

Остановить процедуру и сообщить если:

| # | Критерий | Действие |
|---|---|---|
| S1 | `has_placeholders: True` после заполнения | Перепроверить config — какой плейсхолдер остался |
| S2 | `config_ok: False` | Проверить `config_error` в выводе `doctor` |
| S3 | `permissions_ok: False` | `chmod 600 <AGENT_ROOT>/config/device_secret.dev` |
| S4 | `secret-store-check → present: False` | Повторить Step 5 (secret-store-set) |
| S5 | Backend health check fails | Backend не доступен — Phase B отложить |
| S6 | `agent_config.json` попал в `git status` | `.gitignore` не сработал — STOP, не коммитить |

---

## 6. Rollback (если что-то пошло не так)

### Полный откат Phase B

```bash
# На КСО:
# 1. Удалить agent root полностью
rm -rf <AGENT_ROOT>

# 2. Убедиться
ls <AGENT_ROOT>
# → No such file or directory

# 3. На dev-машине: удалить временный файл (если остался)
shred -u /tmp/agent_config_filled.json 2>/dev/null
```

### Частичный откат (только config)

```bash
# На КСО:
rm <AGENT_ROOT>/config/agent_config.json
# После этого config_status покажет present: False
```

### Частичный откат (только secret)

```bash
# На КСО:
sidecar secret-store-delete --root <AGENT_ROOT> --dev-secret-store
# После этого secret-store-check покажет present: False
```

---

## 7. Safety Gates Verification (post-application)

Перед переходом к Phase C убедиться:

| # | Gate | Команда | Ожидание |
|---|---|---|---|
| V1 | Config без плейсхолдеров | `config-status` | `has_placeholders: False` |
| V2 | Все required поля present | `validate-no-placeholders` | `all_required_present: True` |
| V3 | Secret читаем | `secret-store-check` | `present: True, permissions_ok: True` |
| V4 | Backend hostname валиден | `config-status` | `backend_scheme: https` |
| V5 | Agent root структура ok | `doctor` | `folders_ok: True` |
| V6 | Никаких значений в выводе | Все команды выше | Нет `https://...` (кроме scheme), нет secret |

---

## 8. Что ЗАПРЕЩЕНО на Phase B

| ❌ Запрещено | Почему |
|---|---|
| `sidecar run-once` | Запускает manifest fetch + PoP — это Phase C |
| `sidecar sync-manifest` | Сетевая активность — Phase C |
| `sidecar heartbeat-once` | Отправка данных на backend — Phase C |
| `sidecar sync-runtime-config` | Сетевая активность |
| `sidecar auth-check` | Пытается аутентифицироваться |
| Запись `device_secret.dev` НЕ через stdin | Аргументы команд видны в `ps aux` |
| `git add agent_config.json` | Защита `.gitignore` |
| `echo $DEVICE_SECRET` | Вывод в консоль/логи |
| Копирование `agent_config.json` в репозиторий | Даже с другим именем |
| Запуск X11/Chromium/player | Phase D |

---

## 9. Что остаётся blocked после Phase B

| # | Blocker | Фаза |
|---|---|---|
| 1 | Manifest не синхронизирован | C |
| 2 | Media cache пуст | C |
| 3 | Runtime config не получен | C |
| 4 | Phase D manual approval | D |

---

## 10. Связь с другими документами

| Документ | Роль |
|---|---|
| `test-kso-sidecar-config-preparation.md` | Анализ config mechanisms + template |
| `test-kso-live-backend-seed-runbook.md` | Полный Phase A/B/C runbook |
| `test-kso-live-config-checklist.md` | 12 полей sidecar config |
| `one-kso-e2e-dry-run-readiness-gate.md` | Readiness gate specification |
