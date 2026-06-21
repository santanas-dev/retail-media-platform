# KSO Runtime Release Package Contract

> **Статус:** 📦 Contract — структура, версионирование, проверка целостности.
>
> Последнее обновление: 2026-06-21

---

## Назначение

Определить структуру релизного пакета `kso-runtime`, который ИТ-контур
распространяет по Linux КСО. Пакет содержит player, sidecar, state adapter,
deployment-инфраструктуру (systemd, env examples, bootstrap, preflight)
и документацию.

---

## Структура пакета

```
kso-runtime-<version>.tar.gz
├── VERSION                          # MAJOR.MINOR.PATCH
├── MANIFEST.json                    # Состав пакета, метаданные
├── CHECKSUMS.sha256                 # Хеши всех файлов
├── apps/
│   ├── kso_player/
│   ├── kso_sidecar_agent/
│   └── kso_state_adapter/
├── player_shell/                    # 5 файлов: index.html, styles.css,
│   │                                #   player.js, bootstrap.js, bootstrap_snapshot.js
├── infra/
│   └── kso-linux/
│       ├── systemd/                 # kso-*.service templates
│       ├── env-examples/            # kso-*.env.example
│       ├── install/                 # bootstrap script
│       ├── preflight/               # preflight validator
│       └── release/                 # builder + manifest example (этот контракт)
└── docs/
    └── kso/                         # Документация KSO
```

---

## Что ВХОДИТ в пакет

| Категория | Путь | Комментарий |
|---|---|---|
| Player source | `apps/kso_player/` | Без `player_shell/runtime/`, без `__pycache__/` |
| Sidecar source | `apps/kso_sidecar_agent/` | Без `__pycache__/` |
| State adapter source | `apps/kso_state_adapter/` | Без `__pycache__/` |
| Player shell source | `player_shell/` | 5 immutable файлов |
| Systemd templates | `infra/kso-linux/systemd/` | `.service` файлы |
| Env examples | `infra/kso-linux/env-examples/` | `.env.example` (без реальных значений) |
| Bootstrap | `infra/kso-linux/install/` | `kso_linux_bootstrap.py` |
| Preflight | `infra/kso-linux/preflight/` | `kso_linux_preflight.py` |
| Builder + manifest | `infra/kso-linux/release/` | Этот контракт |
| Docs | `docs/kso/` | Runbook, contract, discovery |
| Version | `VERSION` | Semantic version |
| Manifest | `MANIFEST.json` | Состав + метаданные |
| Checksums | `CHECKSUMS.sha256` | SHA-256 всех файлов |

---

## Что ИСКЛЮЧАЕТСЯ из пакета

| Категория | Почему исключается |
|---|---|
| `*.env` (реальные) | Секреты/токены не должны попадать в пакет |
| `__pycache__/`, `*.pyc` | Артефакты компиляции |
| `.git/` | VCS-данные |
| `state/kso_state.json` | Runtime состояние КСО |
| `manifest/current_manifest.json` | Локальный кеш manifest |
| `media/current/` | Локальный кеш media |
| `pop/pending/`, `pop/sent/` | PoP события |
| `health-*.json` | Health файлы |
| `runtime/player_shell/` | Runtime копия shell |
| `logs/` | Логи сервисов |
| `*.log` | Любые лог-файлы |
| `*.pid` | PID файлы |
| `*.lock` | Lock-файлы |
| `tests/` в apps | Тесты не нужны на production КСО |
| `__pycache__/` | Кеш Python |

---

## Versioning

**Semantic version:** `MAJOR.MINOR.PATCH`

| Компонент | Правило инкремента |
|---|---|
| `MAJOR` | Ломающие изменения контракта (manifest, state, API) |
| `MINOR` | Новые фичи (новый source type, новый daemon feature) |
| `PATCH` | Багфиксы, безопасность, hardening |

**Текущая версия:** `0.1.0` (pre-production)

**Файл VERSION:**
```
0.1.0
```

**MANIFEST.json включает:**
```json
{
  "schema_version": 1,
  "package_name": "kso-runtime",
  "version": "0.1.0",
  "components": [...],
  "created_at_utc": "2026-06-21T00:00:00Z",
  "checksums_file": "CHECKSUMS.sha256"
}
```

---

## CHECKSUMS.sha256

Формат: `<sha256_hex>  <relative/path>`

**Пример:**
```
abc123...  VERSION
def456...  MANIFEST.json
111aaa...  apps/kso_player/kso_player/cli.py
...
```

Хеши считаются от всех файлов пакета, кроме самого `CHECKSUMS.sha256`.

**Проверка (на КСО):**
```bash
cd /opt/verny/kso/releases/<version>
sha256sum -c CHECKSUMS.sha256
```

---

## Хранение

Пакет должен храниться **только** во внутреннем корпоративном хранилище:

| Разрешено | Пример |
|---|---|
| GitLab Releases | `https://gitlab.internal.example/verny/kso/-/releases` |
| Nexus | `https://nexus.internal.example/repository/kso-releases/` |
| Artifactory | `https://artifactory.internal.example/kso-runtime/` |
| Internal MinIO/S3 | `s3://kso-releases/` (внутренний) |
| Internal file share | `smb://files.internal.example/kso/releases/` |

**Запрещено:**
- ❌ GitHub / публичный CDN
- ❌ `curl`/`wget` внешних URL
- ❌ Автообновление из интернета
- ❌ Прямая загрузка с ноутбука разработчика

---

## Install layout на КСО

```
/opt/verny/kso/
├── releases/
│   ├── 0.1.0/                        # Распакованный релиз
│   │   ├── VERSION
│   │   ├── MANIFEST.json
│   │   ├── CHECKSUMS.sha256
│   │   ├── apps/
│   │   ├── player_shell/
│   │   └── infra/
│   ├── 0.0.5/                        # Предыдущий релиз (rollback target)
│   └── ...
├── current -> releases/0.1.0/        # Симлинк на активную версию
├── player_shell/                     # Может быть симлинком на current/player_shell
└── ...
```

**Важно:** `/opt/verny/kso/current` — симлинк. Никогда не перезаписывать
содержимое напрямую. Обновление = новый `releases/<version>/` + переключение симлинка.

---

## Rollback contract

### Порядок rollback

1. `sudo systemctl stop kso-player.service`
2. `sudo systemctl stop kso-sidecar.service`
3. `sudo systemctl stop kso-state-adapter.service`
4. Проверить, что все три `inactive (dead)`
5. Переключить симлинк на предыдущий релиз:
   ```bash
   sudo ln -sfn /opt/verny/kso/releases/0.0.5 /opt/verny/kso/current
   ```
6. Проверить целостность:
   ```bash
   cd /opt/verny/kso/releases/0.0.5
   sha256sum -c CHECKSUMS.sha256
   ```
7. Запустить preflight:
   ```bash
   python3 infra/kso-linux/preflight/kso_linux_preflight.py --target-root /
   ```
8. Запустить сервисы в pilot order:
   - state-adapter → sidecar → player

### Что НЕ удалять при rollback

| Данные | Причина |
|---|---|
| `sent/` PoP | Audit trail — нельзя терять |
| `pending/` PoP | Неотправленные события |
| `media/current/` | Долгая перезагрузка |
| `state/kso_state.json` | Текущее состояние КСО |
| `*.env` (конфигурация) | Только менять source state, не удалять |
| `manifest/current_manifest.json` | Локальный кеш |

### Что МОЖНО удалить

| Данные | Причина |
|---|---|
| `runtime/player_shell/` | Пересоздастся из source shell |
| `health-*.json` | Пересоздадутся при старте |
| Старые `releases/<old>/` | Через N версий после подтверждения |

---

## Package builder

Скрипт: `infra/kso-linux/release/kso_release_package_builder.py`

### Безопасный dry-run (по умолчанию)

```bash
python3 infra/kso-linux/release/kso_release_package_builder.py --dry-run
```

Выводит план: какие файлы войдут в пакет, но **ничего не создаёт**.

### Build в output-dir

```bash
python3 infra/kso-linux/release/kso_release_package_builder.py \
    --build --version 0.1.0 \
    --output-dir /tmp/kso-release
```

Создаёт в `/tmp/kso-release/`:
- `kso-runtime-0.1.0.tar.gz`
- `VERSION`
- `MANIFEST.json`
- `CHECKSUMS.sha256`

**Builder НИКОГДА:**
- ❌ Не пишет в `/opt`, `/etc`, `/var`
- ❌ Не запускает systemctl
- ❌ Не читает `.env` файлы (только `.example`)
- ❌ Не включает runtime data
- ❌ Не включает секреты/токены

---

## Проверка целостности (deployment checklist)

Перед установкой на КСО:

```bash
# 1. Проверить VERSION
cat VERSION
# 0.1.0

# 2. Проверить MANIFEST.json
cat MANIFEST.json | python3 -m json.tool

# 3. Проверить checksums
sha256sum -c CHECKSUMS.sha256
# Все файлы должны быть "OK"

# 4. Проверить, что нет runtime data
# Внутри пакета не должно быть:
find . -name "*.env" ! -name "*.example"  # должно быть пусто
find . -path "*/pop/*"                     # должно быть пусто
find . -path "*/state/*"                   # должно быть пусто
find . -path "*/media/current/*"           # должно быть пусто
```

---

## Безопасность

| Правило | Статус |
|---|---|
| Пакет не содержит секретов | ✅ только `.example` |
| Пакет не содержит runtime data | ✅ |
| Пакет хранится только во внутреннем хранилище | ✅ |
| Нет автообновления из интернета | ✅ |
| Нет `curl`/`wget` внешних URL | ✅ |
| Checksums проверяются перед установкой | ✅ |
| Rollback через symlink + preflight | ✅ |
| PoP/cache не удаляются при rollback | ✅ |
| `current` — всегда симлинк | ✅ |

---

## Ссылки

- `infra/kso-linux/README.md` — Deployment guide
- `docs/kso/linux-kso-pilot-first-start-runbook.md` — Pilot runbook
- `docs/kso/ukm4-state-source-discovery.md` — UKM 4 discovery
