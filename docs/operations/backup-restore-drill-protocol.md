# Backup & Restore Drill Protocol

**Version:** 1.0 | **Date:** 2026-07-01 | **Owner:** Ops Team

> **SCOPE:** Lab/stage environment only. **DOES NOT** touch production DB.  
> **STATUS:** ⬜ Not yet executed — protocol ready.

---

## Safety Rules

1. **Lab/stage only** — use `PGDATABASE=retail_media_stage` or equivalent
2. **Never restore against production DB** without full approval chain
3. **CONFIRM_RESTORE=yes** required for all non-dry-run restores
4. All operations are **destructive** — verify target DB before proceeding
5. Keep terminal output as evidence

---

## Environment Setup

```bash
# Set environment (use lab/stage values — NO PRODUCTION)
export PGHOST=<LAB_PG_HOST>
export PGPORT=<LAB_PG_PORT>
export PGDATABASE=<LAB_DB_NAME>
export PGUSER=<LAB_PG_USER>
export PGPASSWORD=<LAB_PG_PASSWORD>
export BACKUP_DIR=<BACKUP_DIRECTORY>
export CONFIRM_RESTORE=yes
```

---

## Drill Sequence

### Phase 1: Pre-Drill Verification

| # | Check | Command | Expected | Result |
|---|---|---|---|---|
| 1.1 | PostgreSQL reachable | `pg_isready -h $PGHOST -p $PGPORT` | accepting connections | ⬜ |
| 1.2 | Database exists | `psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -c "SELECT 1"` | 1 row | ⬜ |
| 1.3 | Tables present | `psql ... -c "\dt"` | Tables listed | ⬜ |
| 1.4 | Row count | `psql ... -c "SELECT count(*) FROM users"` | > 0 | ⬜ |
| 1.5 | Backup directory writable | `mkdir -p $BACKUP_DIR && touch $BACKUP_DIR/test` | File created | ⬜ |
| 1.6 | `mc` available (MinIO) | `mc --version` | Version output | ⬜ |

### Phase 2: Backup Execution

| # | Step | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 2.1 | Dry-run backup | `bash scripts/ops/backup_postgres.sh --dry-run` | Prints dry-run message | ⬜ | Terminal |
| 2.2 | Execute backup | `bash scripts/ops/backup_postgres.sh` | "Backup complete" | ⬜ | Terminal |
| 2.3 | Backup file exists | `ls -lh $BACKUP_DIR/retail_media_*.dump` | File > 1 KB | ⬜ | Terminal |
| 2.4 | Backup file checksum | `sha256sum $BACKUP_DIR/retail_media_*.dump` | Hash recorded | ⬜ | Terminal |

**RPO measurement (start):** `date -u +%Y-%m-%dT%H:%M:%SZ` → ______________

### Phase 3: Intentional Data Change

| # | Step | Command | Expected | Result |
|---|---|---|---|---|
| 3.1 | Insert test row | `INSERT INTO seed_log (key, value) VALUES ('drill_test', 'before_restore')` | INSERT 1 | ⬜ |
| 3.2 | Verify row exists | `SELECT * FROM seed_log WHERE key = 'drill_test'` | 1 row | ⬜ |
| 3.3 | Record timestamp | `date -u +%Y-%m-%dT%H:%M:%SZ` → ______________ | — | ⬜ |

### Phase 4: Restore Execution

| # | Step | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 4.1 | Dry-run restore | `BACKUP_FILE=... bash scripts/ops/restore_postgres.sh --dry-run` | Prints dry-run | ⬜ | Terminal |
| 4.2 | Confirm restore (5s warning) | `BACKUP_FILE=... CONFIRM_RESTORE=yes bash scripts/ops/restore_postgres.sh` | "Press Ctrl+C" → continues | ⬜ | Terminal |
| 4.3 | Restore complete | Script output | "Restore complete" | ⬜ | Terminal |

### Phase 5: Post-Restore Validation

| # | Check | Command | Expected | Result |
|---|---|---|---|---|
| 5.1 | Database reachable | `psql ... -c "SELECT 1"` | 1 row | ⬜ |
| 5.2 | Test row gone | `SELECT * FROM seed_log WHERE key = 'drill_test'` | 0 rows | ⬜ |
| 5.3 | Users table restored | `SELECT count(*) FROM users` | Same as pre-backup count | ⬜ |
| 5.4 | Roles table restored | `SELECT count(*) FROM roles` | 8 roles | ⬜ |
| 5.5 | Permissions restored | `SELECT count(*) FROM permissions` | ~50 permissions | ⬜ |
| 5.6 | Seed idempotent re-run | `python -m app.domains.identity.seed` | "Seed complete" | ⬜ |
| 5.7 | Health check | `curl $BACKEND_URL/api/health/ready` | HTTP 200 | ⬜ |

**RPO measurement (end):** `date -u +%Y-%m-%dT%H:%M:%SZ` → ______________  
**RTO measurement:** End time − Start time = ______ seconds

---

## MinIO Backup Drill (Optional)

| # | Step | Command | Expected | Result |
|---|---|---|---|---|
| M.1 | Dry-run MinIO backup | `bash scripts/ops/backup_minio.sh --dry-run` | Prints dry-run | ⬜ |
| M.2 | Execute MinIO backup | `bash scripts/ops/backup_minio.sh` | "Backup complete" | ⬜ |
| M.3 | Verify files | `ls -lh $BACKUP_DIR/$MINIO_BUCKET/` | Files listed | ⬜ |

---

## Failure Handling

If restore fails:
1. Check PostgreSQL error logs: `tail -50 /var/log/postgresql/...`
2. Verify backup file integrity: `sha256sum $BACKUP_FILE`
3. Check disk space: `df -h`
4. Verify pg_restore version matches pg_dump version
5. **DO NOT PROCEED** to production restore
6. Document failure in drill report

---

## Evidence & Approval

| Artifact | Collected |
|---|---|
| Backup dry-run terminal output | ⬜ |
| Backup execution terminal output | ⬜ |
| Backup file checksum | ⬜ |
| Pre-restore DB state (row counts) | ⬜ |
| Restore dry-run terminal output | ⬜ |
| Restore execution terminal output | ⬜ |
| Post-restore validation (row counts) | ⬜ |
| RPO measurement | ⬜ |
| RTO measurement | ⬜ |
| MinIO backup evidence (optional) | ⬜ |

---

## Decision

| Gate | Result |
|---|---|
| Backup/restore drill passed | ⬜ Yes / ⬜ No |
| RPO achieved | ______ seconds |
| RTO achieved | ______ seconds |
| Failures encountered | ______________ |
| Ready for production restore procedure | ⬜ Yes / ⬜ No |
| Approver | ______________ | Date: __-__-__ |
