# B3 — Backup Command Output (Sanitized)

**Date:** 2026-07-02

## backup_postgres.sh --help

```
Usage: PGHOST=... PGDATABASE=... PGUSER=... PGPASSWORD=*** BACKUP_DIR=... bash backup_postgres.sh [--dry-run]
  --dry-run   Print what would be done without executing
  --help      This message
```

## backup_postgres.sh --dry-run

```
[DRY-RUN] Would backup <DATABASE> to <BACKUP_DIR>/retail_media_<TIMESTAMP>.dump
[DRY-RUN] Command: pg_dump -h <HOST> -U <USER> -d <DATABASE> --format=custom -f <FILE>
```

## backup_minio.sh --dry-run

```
WARNING: 'mc' (MinIO Client) not found.
[DRY-RUN] Would use mc to mirror bucket.
```

## Safety Checks

- [x] PGPASSWORD not echoed
- [x] No real credentials
- [x] No production hostnames
- [x] BACKUP_DIR required (script exits if unset)
- [x] PGDATABASE/PGHOST/PGUSER required
- [x] PGPASSWORD checked for empty
- [x] Output: `retail_media_YYYYMMDD_HHMMSS.dump`
