# Mini-Design: KSO Sidecar Agent — Secret Storage

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25.4
**Дата:** 18 июня 2026
**Основание:** `docs/kso_sidecar_agent_design.md` §9

---

## 1. Goal

Спроектировать безопасное хранение `device_secret` (и будущих токенов/ключей) для KSO Sidecar Agent. Определить, какие данные — secret, какие — non-secret, и как хранить каждый класс.

**Важно:** `config/agent_config.json` (Шаг 25.3) уже реализован как **non-secret** config. В нём есть `device_code` (не секрет), но туда запрещено класть `device_secret`, JWT, token, password, api_key, private_key.

**На этом шаге код не пишем.**

---

## 2. Secret / Non-Secret Classification

### 2.1 Secrets (хранить ТОЛЬКО в защищённом хранилище)

| Данные | Тип | Хранение | Ротация |
|---|---|---|---|
| `device_secret` | Строка (например, 32 hex) | OS-protected storage или 0400-файл | Ручная через админку backend |
| JWT access token | Short-lived строка | Только память процесса | Автоматически (refresh) |
| JWT refresh token (если появится) | Строка | Только память процесса (или OS keychain) | При refresh |
| Private key (mTLS, если появится) | Ключ | OS keychain / TPM | По расписанию |
| Client credential (OAuth2, если появится) | Строка | OS-protected storage | По расписанию |

### 2.2 Non-secrets (хранить в `config/agent_config.json` или файлах агента)

| Данные | Где | Примечание |
|---|---|---|
| `device_code` | `config/agent_config.json` | Не секрет, но ограничить права чтения (0600) |
| `backend_base_url` | `config/agent_config.json` | Не секрет |
| `tls_verify` | `config/agent_config.json` | Не секрет |
| `request_timeout_sec` | `config/agent_config.json` | Не секрет |
| `local_interface_version` | `config/agent_config.json` | Не секрет |
| Runtime config | `config/runtime_config.json` (из backend) | Без secrets |
| Manifest | `manifest/current_manifest.json` | Без secrets |
| Media metadata | `manifest/current_manifest.json` | Без secrets |
| Agent status | `status/agent_status.json` | Без secrets |
| PoP events | `pop/events.log` | Без secrets, без customer/payment данных |

---

## 3. Жёсткие запреты

В этом разделе фиксируем, **куда никогда не должны попадать secrets**. Этот список должен проверяться тестами на этапе реализации.

| # | Запрет | Почему |
|---|---|---|
| 1 | ❌ Не хранить `device_secret` в `config/agent_config.json` | Уже реализовано — валидация `local_config.py` reject forbidden substrings |
| 2 | ❌ Не хранить JWT/access token на диске | Token short-lived — потеря security при утечке диска |
| 3 | ❌ Не хранить refresh token на диске без отдельного решения | Если появится — отдельный design |
| 4 | ❌ Не писать secrets в `logs/agent.log` | Реализовано — `safe_logger.py` → `[REDACTED]` |
| 5 | ❌ Не писать secrets в `status/agent_status.json` | Реализовано — `agent_status.py` reject forbidden substrings |
| 6 | ❌ Не писать secrets в `doctor` output | Doctor не читает secret storage |
| 7 | ❌ Не включать secrets в crash/error messages | Исключения валидации не раскрывают значения полей |
| 8 | ❌ Не отправлять secrets в local interface folder (для КСО ПО) | КСО ПО не должно иметь доступ к secret storage |
| 9 | ❌ КСО ПО не должно иметь доступ к secret storage | Отдельный процесс, отдельные права |
| 10 | ❌ Не передавать `device_secret` через CLI-аргументы | Аргументы видны в `/proc/<pid>/cmdline` и `ps` |

---

## 4. Linux — Варианты хранения

### 4.1 Вариант A: systemd `LoadCredential=` / `${CREDENTIALS_DIRECTORY}`

**Описание:** systemd загружает credential из защищённого источника в память и передаёт процессу через файл в `${CREDENTIALS_DIRECTORY}` (tmpfs, права 0000 кроме процесса).

| Аспект | Оценка |
|---|---|
| **Плюсы** | Максимальная безопасность. Нет на диске. systemd контролирует доступ. Автоматическая очистка при остановке сервиса. |
| **Минусы** | Требует systemd (не везде). Требует root для `systemctl set-creds`. |
| **Требования** | systemd ≥ 247. Сервис-файл с `LoadCredential=device_secret:/etc/kso-agent/device.secret`. |
| **Риск** | Низкий. Если злоумышленник имеет root — он может прочитать credential через systemd API. |
| **Применимость** | **Рекомендуется для production**, если КСО на Linux с systemd. |

### 4.2 Вариант B: root-owned file 0600 вне общей папки КСО

**Описание:** `device_secret` хранится в отдельном файле с правами 0400, владелец `kso-agent`, **вне** папки `kso-adapter/` (которая доступна КСО ПО). Например: `/etc/kso-agent/device.secret`.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Просто. Не требует systemd. Работает на любом Linux. |
| **Минусы** | Secret на диске. Нужен механизм деплоя (Ansible/скрипт). Нет автоматической очистки. |
| **Требования** | Возможность создать файл с 0400 от имени `kso-agent`. Папка `/etc/kso-agent/` с 0700. |
| **Риск** | Средний. Если злоумышленник читает диск — secret раскрыт. Файл виден в backup'ах. |
| **Применимость** | **Рекомендуется как fallback**, если systemd недоступен. |

### 4.3 Вариант C: OS keyring (GNOME Keyring / KWallet / Secret Service API)

**Описание:** Использовать D-Bus Secret Service API или keyring-библиотеку для хранения в зашифрованном keyring пользователя.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Зашифрованное хранение. Интеграция с DE. Разблокируется при логине. |
| **Минусы** | Требует графическую сессию (не всегда на КСО). Зависимость от DE. API может меняться. |
| **Требования** | D-Bus session bus. Установленный keyring daemon. |
| **Риск** | Средний. Keyring разблокирован пока пользователь залогинен. При kiosk-режиме — неясно. |
| **Применимость** | **Не рекомендуется для v1.** Слишком много зависимостей от DE. |

### 4.4 Вариант D: Dev-only fallback (plain file с явным разрешением)

**Описание:** Для локальной разработки (НЕ production) — хранить `device_secret` в `config/device_secret` с правами 0600, только если передан флаг `--dev-secret-store` или переменная `KSO_DEV_SECRET_STORE=1`.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Быстро для разработки. Не требует systemd/root. |
| **Минусы** | **Категорически не для production.** Secret на диске в общей папке. |
| **Требования** | Явный флаг. Предупреждение при старте. |
| **Риск** | Высокий для production. Приемлемый для dev (изолированная среда). |
| **Применимость** | **Только dev.** Агент должен отказаться стартовать в production-режиме с этим флагом. |

---

## 5. Windows — Варианты хранения

### 5.1 Вариант A: DPAPI (Data Protection API)

**Описание:** `CryptProtectData` / `CryptUnprotectData` с флагом `CRYPTPROTECT_LOCAL_MACHINE`. Данные шифруются ключом, привязанным к машине (или пользователю). Хранить зашифрованный блоб в реестре или файле.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Встроено в Windows. Прозрачное шифрование. Привязка к машине (CurrentMachine) или пользователю (CurrentUser). |
| **Минусы** | При CurrentMachine — любой процесс на машине может расшифровать (но не удалённо). При CurrentUser — нужна сессия пользователя. |
| **Требования** | Windows XP+. Права на `CryptProtectData`. |
| **Риск** | Низкий. Если malware работает под тем же пользователем — может расшифровать. Но не через файловую систему. |
| **Применимость** | **Рекомендуется для production.** Лучше `CurrentMachine` для сервисов. |

### 5.2 Вариант B: Windows Credential Manager

**Описание:** `CredWrite` / `CredRead` API. Хранит credentials в защищённом хранилище Windows, доступном через Control Panel → Credential Manager.

| Аспект | Оценка |
|---|---|
| **Плюсы** | Стандартное Windows-хранилище. UI для администратора. Поддержка доменных учёток. |
| **Минусы** | Требует интерактивную сессию для UI. API сложнее DPAPI. |
| **Требования** | Права на `CredWrite`. Тип credential: `CRED_TYPE_GENERIC`. |
| **Риск** | Низкий. Аналогично DPAPI — локальный процесс может прочитать. |
| **Применимость** | **Альтернатива DPAPI**, если нужен UI для администратора. |

### 5.3 Вариант C: ACL file только для service account

**Описание:** Файл с ACL, разрешающим чтение только для SYSTEM и конкретного service account (`NT SERVICE\kso-agent`).

| Аспект | Оценка |
|---|---|
| **Плюсы** | Просто. Не требует шифрования. |
| **Минусы** | Secret на диске. ACL сложнее настроить правильно. |
| **Требования** | Права на изменение ACL. Service account должен существовать. |
| **Риск** | Средний. Ошибки в ACL → secret раскрыт. |
| **Применимость** | **Fallback**, если DPAPI недоступен. |

### 5.4 Вариант D: Dev-only fallback

**Описание:** Аналогично Linux — plain file с флагом `--dev-secret-store` или `KSO_DEV_SECRET_STORE=1`. **Запрещён для production.**

| Аспект | Оценка |
|---|---|
| **Плюсы** | Быстро для разработки. |
| **Минусы** | Не для production. |
| **Риск** | Высокий для production. |
| **Применимость** | **Только dev.** |

---

## 6. Рекомендация

### 6.1 Production

| ОС | Primary | Fallback |
|---|---|---|
| **Linux** | systemd `LoadCredential=` / `${CREDENTIALS_DIRECTORY}` | root-owned file 0400 в `/etc/kso-agent/` вне local interface root |
| **Windows** | DPAPI `CryptProtectData` (CurrentMachine) | ACL file только для service account |

### 6.2 Development

- **Linux + Windows:** Явный dev-only файл `config/device_secret` с правами 0600
- **Требуется:** `--dev-secret-store` флаг или `KSO_DEV_SECRET_STORE=1`
- **Agent отказывается стартовать** в production (без флага) если обнаружен dev-only secret file
- **Agent выводит WARNING** при старте с dev-only режимом

### 6.3 Важное замечание

Точное решение зависит от:
- ОС КСО (неизвестна — вопрос поставщику)
- Наличия systemd на Linux
- Наличия прав на создание service account на Windows
- Требований сертификации кассового ПО

**→ См. `docs/kso_vendor_integration_questions.md` вопрос #10 (secure storage) и #5 (права процесса).**

---

## 7. Secret не должен быть в local interface root

**Критически важно:** КСО ПО имеет read-only доступ к `media/current/`, `manifest/`, `status/`. Secret storage **не должен** быть внутри этой папки.

```
/var/lib/kso-adapter/          ← local interface root (КСО ПО имеет доступ)
├── config/                    ← КСО ПО: нет доступа
│   ├── agent_config.json      ← non-secret ✓
│   ├── runtime_config.json    ← non-secret ✓
│   └── device_secret          ← ❌ ЗАПРЕЩЕНО здесь!
├── media/current/             ← КСО ПО: read
├── manifest/                  ← КСО ПО: read
├── pop/                       ← КСО ПО: append
├── status/                    ← КСО ПО: read
└── logs/                      ← КСО ПО: read

/etc/kso-agent/                ← ТОЛЬКО agent (0700, kso-agent:kso-agent)
└── device.secret              ← 0400 ✓
```

---

## 8. Ротация секрета

### 8.1 Ручная ротация (единственный вариант v1)

1. Администратор backend создаёт новый credential через `POST /admin/gateway-devices/{id}/credentials`
2. Администратор КСО обновляет secret в защищённом хранилище
3. Администратор backend отзывает старый credential через `POST .../credentials/{id}/revoke`
4. Agent при следующей попытке auth со старым secret получает 401 → alert → администратор обновляет

### 8.2 Автоматическая ротация (v2+)

- Не в v1. Требует endpoint обновления secret или механизм временных токенов.
- Рассмотреть, когда будет известна ОС КСО и механизм деплоя.

---

## 9. Удаление секрета

- **Linux:** `shred -u /etc/kso-agent/device.secret` или `systemctl set-creds --unset`
- **Windows:** `CredDelete` или удаление DPAPI блоба из реестра/файла
- **Dev:** удалить файл
- Agent при старте без secret должен выдать понятную ошибку и НЕ стартовать

---

## 10. Backup / Restore ограничения

- Secret storage **не должен** попадать в backup папки `kso-adapter/`
- `/etc/kso-agent/` — нужно явно исключить из backup (на уровне скриптов backup)
- Windows DPAPI блоб в реестре — может попасть в system state backup (это OK, DPAPI ключ другой на restore)
- При restore на другую машину — secret нужно обновить вручную

---

## 11. Логирование

Agent **уже реализовал** safe logger (`safe_logger.py`):

- При логировании сообщения с forbidden substrings → заменяется на `[REDACTED]`
- Forbidden: token, jwt, password, secret, api_key, private_key, payment_card, receipt

Дополнительные требования для secret storage:

- Никогда не логировать содержимое файла `device.secret`
- При ошибке чтения secret: логировать "Cannot read device secret", но не путь к файлу
- При ошибке DPAPI/Credential Manager: логировать "DPAPI decrypt failed", без деталей
- Не логировать значение secret даже в DEBUG-режиме

---

## 12. Threat Model

| # | Угроза | Вектор | Вероятность | Влияние | Митигация |
|---|---|---|---|---|---|
| 1 | Пользователь КСО читает secret file | `cat /etc/kso-agent/device.secret` | Средняя | Высокое | Права 0400, владелец kso-agent |
| 2 | КСО ПО читает secret | Читает файл в общей папке | Средняя | Высокое | Secret storage **вне** local interface root |
| 3 | Secret попадает в logs | Логирование значения | Низкая | Высокое | `safe_logger.py` → `[REDACTED]` |
| 4 | Secret попадает в agent_status.json | Ошибка в коде | Низкая | Высокое | Валидация reject forbidden substrings |
| 5 | Secret попадает в Git | `git add` файла | Средняя | Критическое | `.gitignore` на secret storage папку |
| 6 | Secret попадает в backup | Backup директории `/etc/` | Средняя | Высокое | Документировать исключение из backup |
| 7 | Secret остаётся после удаления agent | Не удалён файл | Низкая | Среднее | Инструкция по удалению |
| 8 | Malware на КСО читает secret | Доступ к ФС/памяти процесса | Высокая (если malware уже есть) | Критическое | Minimal attack surface agent. OS-level защита. |
| 9 | Неправильные ACL | `chmod 644` по ошибке | Средняя | Высокое | Тесты проверяют права. Doctor проверяет. |
| 10 | Debug output раскрывает secret | `print(secret)` в коде | Низкая | Высокое | Code review. Security leakage тесты. |

---

## 13. Будущие CLI-команды (НЕ реализовывать сейчас)

Команды для будущего модуля `secret_store.py`:

| Команда | Описание | Интерактивность |
|---|---|---|
| `secret-store init` | Инициализировать secret storage (создать папку/реестр, проверить права) | ❌ CLI |
| `secret-store set-device-secret` | Сохранить device_secret через stdin или `KSO_DEVICE_SECRET` env | ✅ stdin (НЕ аргумент!) |
| `secret-store check` | Проверить, что secret доступен и storage защищён | ❌ CLI |
| `secret-store rotate` | Заменить secret (старый + новый через stdin) | ✅ stdin |
| `secret-store delete` | Удалить secret из storage | ❌ CLI (с подтверждением) |

**Почему нельзя передавать secret через CLI-аргументы:**

- Аргументы командной строки видны в `/proc/<pid>/cmdline` (Linux)
- Аргументы видны в Task Manager / Process Explorer (Windows)
- Аргументы попадают в историю shell
- Аргументы могут быть залогированы systemd journal / Event Log

**Разрешённые способы передачи secret (будущая реализация):**

- ✅ `stdin`: `echo "$SECRET" | kso-agent secret-store set-device-secret`
- ✅ Environment variable: `KSO_DEVICE_SECRET=... kso-agent secret-store set-device-secret`
- ✅ systemd `LoadCredential=` (автоматически при старте сервиса)
- ❌ CLI argument: `--device-secret abc123` — **запрещено**

---

## 14. Будущие тесты (НЕ реализовывать сейчас)

Когда secret storage будет реализован, следующие тесты должны быть написаны:

### 14.1 Security Leakage Tests

| # | Тест | Проверка |
|---|---|---|
| 1 | Secret не попадает в `agent_config.json` | `grep -r <secret_hash> config/` → empty |
| 2 | Secret не попадает в `agent_status.json` | `grep -r <secret_hash> status/` → empty |
| 3 | Secret не попадает в `logs/agent.log` | `grep -r <secret_hash> logs/` → empty |
| 4 | Doctor не печатает secret | `kso-agent doctor 2>&1 \| grep <secret_hash>` → empty |
| 5 | Secret не попадает в crash report | Trigger error → output → grep |
| 6 | Secret не в аргументах процесса | `ps aux \| grep kso-agent \| grep <secret_hash>` → empty |

### 14.2 Permission Tests

| # | Тест | Проверка |
|---|---|---|
| 7 | Secret file permissions = 0400 | `stat -c %a <secret_file>` → `400` |
| 8 | Symlink secret file — reject | Создать symlink → `secret-store set` → ошибка |
| 9 | World-readable secret file — reject | `chmod 644` → `secret-store check` → ошибка |
| 10 | Parent directory permissions = 0700 | `stat -c %a <secret_dir>` → `700` |

### 14.3 CLI / Input Tests

| # | Тест | Проверка |
|---|---|---|
| 11 | CLI аргумент `--device-secret` — reject | `kso-agent ... --device-secret abc` → ошибка |
| 12 | Secret через stdin — работает | `echo "test_secret" \| kso-agent secret-store set-device-secret` → OK |
| 13 | Secret через env — работает | `KSO_DEVICE_SECRET=test kso-agent secret-store set-device-secret` → OK |

### 14.4 Lifecycle Tests

| # | Тест | Проверка |
|---|---|---|
| 14 | Rotation не оставляет старые `.tmp` файлы | После rotate → нет `.tmp` в secret dir |
| 15 | Delete удаляет secret | `secret-store delete` → `secret-store check` → MISSING |
| 16 | Dev-only отказывается в production | Без `--dev-secret-store` → ошибка |

---

## 15. Что НЕ реализуем на этом шаге

Документ — **только mini-design**. В рамках Шага 25.4 мы **НЕ реализуем**:

- ❌ Код secret storage (`secret_store.py`)
- ❌ Device auth (JWT, `/auth/token`)
- ❌ Backend calls
- ❌ JWT handling / refresh
- ❌ Encryption (DPAPI, AES)
- ❌ Installer
- ❌ Windows service
- ❌ systemd unit
- ❌ CLI команды `secret-store *`
- ❌ Интерактивный ввод secret

---

## 16. Связанные документы

- `docs/kso_sidecar_agent_design.md` §9 — Secrets / Secure Storage в общем design
- `docs/kso_local_interface_contract.md` §7 — Что запрещено в PoP/Status
- `apps/kso_sidecar_agent/kso_sidecar_agent/local_config.py` — реализованный non-secret config
- `apps/kso_sidecar_agent/kso_sidecar_agent/safe_logger.py` — реализованный safe logger
- `apps/kso_sidecar_agent/kso_sidecar_agent/agent_status.py` — реализованный status с forbidden reject
- `docs/kso_vendor_integration_questions.md` — вопросы поставщику (ОС, secure storage)

---

*Документ создан: 18 июня 2026. Следующий шаг: утверждение → реализация `secret_store.py`.*
