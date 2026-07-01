# H.3 — Deployment / Rollback / Backup Readiness

**Date:** 2026-07-02 | **Phase:** H (Production Readiness) | **Step:** H.3  
**Status:** ✅ COMPLETED  
**Prerequisite:** H.2 Observability & Health Checks  

---

## Summary

Созданы ops-скрипты, шаблоны конфигурации, deployment checklist.  
Обновлены rollback и backup/restore runbooks.

**Никаких production deploy/restore не выполнялось.**  
Production switch, ClickHouse, Docker/.env — не менялись.

---

## Scripts Created (6)

| Script | Назначение | Dry‑run | Safety |
|---|---|---|---|
| `scripts/ops/backup_postgres.sh` | pg_dump backup | ✅ | No PGPASSWORD echo |
| `scripts/ops/restore_postgres.sh` | pg_restore (destructive) | ✅ | CONFIRM_RESTORE=yes required |
| `scripts/ops/backup_minio.sh` | MinIO mirror | ✅ | mc check only |
| `scripts/ops/deploy_preflight.sh` | Pre-deploy checks | ✅ | Read-only |
| `scripts/ops/post_deploy_smoke.sh` | Health endpoint smoke | ✅ | No auth secrets |
| `scripts/ops/rollback_preflight.sh` | Rollback readiness | ✅ | Requires approval + target |

---

## Example Configs (2)

| Файл | Содержит |
|---|---|
| `docs/operations/examples/backup.env.example` | PGHOST, BACKUP_DIR, MINIO placeholders |
| `docs/operations/examples/deploy.env.example` | BACKEND_URL, approval, rollback placeholders |

**Никаких реальных credentials/hostnames/passwords.** Только `<PLACEHOLDER>`.

---

## Docs Created / Updated

| Файл | Действие |
|---|---|
| `docs/operations/deployment-readiness-checklist.md` | 🆕 Pre‑deploy/smoke/rollback/audit |
| `docs/operations/rollback-runbook.md` | 🔄 (already had H.1 content) |
| `docs/operations/backup-restore-runbook.md` | 🔄 (already had H.1 content) |

---

## Dry-Run Philosophy

Все 6 скриптов поддерживают `--dry-run`: 
- Печатают что сделали бы, без реального выполнения
- Не требуют credentials для dry-run
- Restore требует `CONFIRM_RESTORE=yes` для не‑dry‑run

---

## Restore Safety

- `CONFIRM_RESTORE=yes` — обязателен
- 5‑секундное предупреждение перед выполнением
- `dropdb`/`createdb` только после подтверждения
- No hardcoded DROP без guard

---

## Test Results

| Слой | Результат |
|---|---|
| **H.3 targeted** | **54/54** ✅ |
| Backend collection | Unchanged (scripts + docs only) |

---

## Boundaries Confirmed

| Проверка | Статус |
|---|---|
| No Docker/.env changes | ✅ |
| No docker-compose changes | ✅ |
| No migrations | ✅ |
| No DB schema changes | ✅ |
| No backend runtime changes | ✅ |
| No portal changes | ✅ |
| No ClickHouse | ✅ |
| No publication flow | ✅ |
| No KSO/Gateway | ✅ |
| No emergency execution | ✅ |
| No real restore executed | ✅ |
| No production deploy executed | ✅ |
| No real credentials in scripts | ✅ |

---

## Pending

- Actual backup/restore drill on real environment (H.5+)
- Automated deployment (H.4/H.5)
- Rate limiting (H.4)
- Credential rotation (H.4)

---

## GO / NO-GO

### ✅ GO для H.4 — Security Hardening / Access Review

### ❌ NO-GO для:
- Production switch
- ClickHouse
- Real emergency execution
- Production deploy without approval
