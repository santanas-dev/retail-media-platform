# B3 — Backup / Restore Drill Report

**Date:** 2026-07-02 | **Status:** 🟡 DRY-RUN VERIFIED — real drill NOT executed
**⚠️** Real drill requires lab/stage DB credentials and CONFIRM_RESTORE=yes.

## Script Verification

All 6 ops scripts verified with --help and --dry-run:

| Script | --help | --dry-run | Notes |
|---|---|---|---|
| `backup_postgres.sh` | ✅ | ✅ | PGPASSWORD not echoed |
| `restore_postgres.sh` | ✅ | ✅ | CONFIRM_RESTORE=yes required; 5s warning |
| `backup_minio.sh` | ✅ | ✅ | mc not installed (expected) |
| `deploy_preflight.sh` | ✅ | ✅ | Read-only |
| `post_deploy_smoke.sh` | ✅ | ✅ | No auth secrets |
| `rollback_preflight.sh` | ✅ | ✅ | ROLLBACK_APPROVAL required |

## Dry-Run Output

### backup_postgres.sh --dry-run
```
[DRY-RUN] Would backup <DB> to <BACKUP_DIR>/retail_media_<TIMESTAMP>.dump
[DRY-RUN] Command: pg_dump -h <HOST> -U <USER> -d <DB> --format=custom -f <FILE>
```

### restore_postgres.sh --dry-run
```
[DRY-RUN] Would restore <FILE> to <DB>
[DRY-RUN] Steps: dropdb → createdb → pg_restore
```

### backup_minio.sh --dry-run
```
WARNING: 'mc' (MinIO Client) not found.
[DRY-RUN] Would use mc to mirror bucket.
```

## No-Secrets Verification

- ✅ backup_postgres.sh: PGPASSWORD not echoed
- ✅ restore_postgres.sh: PGPASSWORD not echoed
- ✅ backup_minio.sh: no credentials echoed
- ✅ No production hostnames in dry-run output

## Real Drill — Not Executed

**Why:** Requires lab/stage DB credentials + CONFIRM_RESTORE=yes.  
**Protocol:** `docs/operations/backup-restore-drill-protocol.md` (5 phases).

## Decision

- Scripts verified: ✅ All 6 pass --help + --dry-run
- No-secrets confirmed: ✅
- Real drill: ⬜ PENDING lab/stage environment
- Go for real drill: 🟢 YES
