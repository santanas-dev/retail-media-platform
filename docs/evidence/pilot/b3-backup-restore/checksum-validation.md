# B3 — Checksum Validation

**Date:** 2026-07-02 | **Status:** ⬜ NOT EXECUTED — real drill not done

## Checksum Protocol

1. After backup: `sha256sum <BACKUP_DIR>/retail_media_*.dump > backup.sha256`
2. Before restore: `sha256sum -c backup.sha256` → verify integrity
3. After restore: re-dump and compare checksums

## Steps

```bash
# Step 1: Record pre-restore checksum
sha256sum $BACKUP_FILE > pre_restore.sha256

# Step 2: Restore
CONFIRM_RESTORE=yes bash scripts/ops/restore_postgres.sh

# Step 3: Re-backup after restore
bash scripts/ops/backup_postgres.sh
NEW_BACKUP=$(ls -t $BACKUP_DIR/retail_media_*.dump | head -1)

# Step 4: Compare
sha256sum $NEW_BACKUP > post_restore.sha256
diff pre_restore.sha256 post_restore.sha256
```

## Status

- Protocol: ✅ Ready
- Execution: ⬜ Pending real drill
