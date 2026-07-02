# B3 — Restore Command Output (Sanitized)

**Date:** 2026-07-02

## restore_postgres.sh --help

```
Usage: PGHOST=... PGDATABASE=... PGPASSWORD=*** PGUSER=... BACKUP_FILE=... CONFIRM_RESTORE=yes bash restore_postgres.sh [--dry-run]
  --dry-run   Print what would be done without executing
  --help      This message

WARNING: DESTRUCTIVE — drops and recreates the database.
Requires CONFIRM_RESTORE=yes for non-dry-run execution.
```

## restore_postgres.sh --dry-run

```
[DRY-RUN] Would restore <BACKUP_FILE> to <DATABASE>
[DRY-RUN] Steps: dropdb → createdb → pg_restore
```

## Safety Checks

- [x] CONFIRM_RESTORE=yes required
- [x] 5-second warning before destructive operation
- [x] Backup file existence checked
- [x] No DROP without CONFIRM_RESTORE guard
- [x] PGPASSWORD not echoed
- [x] No production hostnames
- [x] Post-restore: alembic upgrade head, seed, health check

## Rejection Without Confirmation

Script exits with ERROR:
```
ERROR: CONFIRM_RESTORE must be set to 'yes' for non-dry-run execution.
This is a DESTRUCTIVE operation.
```
✅ Confirmed: refuses without confirmation.
