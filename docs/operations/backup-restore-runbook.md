# Backup & Restore Runbook

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> **Current Status:** ❌ NOT IMPLEMENTED — runbook created, actual backups not configured.

---

## 1. PostgreSQL Backup

### Scheduled Backup (pg_dump)

```bash
# Daily full backup
pg_dump -h <PG_HOST> -U <PG_USER> -d retail_media \
  --no-password --format=custom \
  -f /backups/pg/retail_media_$(date +%Y%m%d).dump

# Retention: 7 daily + 4 weekly
find /backups/pg/ -name "*.dump" -mtime +30 -delete
```

### WAL Archiving (for PITR)

```ini
# postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /backups/pg/wal/%f && cp %p /backups/pg/wal/%f'
```

**Status:** ❌ Not configured.

---

## 2. Restore Drill

### Full Restore

```bash
# Stop application
docker stop <backend_container>

# Drop and recreate
dropdb -h <PG_HOST> -U <PG_USER> retail_media
createdb -h <PG_HOST> -U <PG_USER> retail_media

# Restore
pg_restore -h <PG_HOST> -U <PG_USER> -d retail_media \
  --no-password --clean --if-exists \
  /backups/pg/retail_media_YYYYMMDD.dump

# Run migrations (if schema changed since backup)
alembic upgrade head

# Seed idempotent (re-creates permissions/roles if missing)
python -m app.domains.identity.seed

# Start application
docker start <backend_container>

# Verify
curl <BACKEND_URL>/health
# Run smoke tests
python -m pytest tests/test_health.py -q
```

**Drill required:** Monthly, evidence logged.

---

## 3. MinIO Backup

```bash
# Mirror bucket to backup location
mc mirror retail-media/creatives /backups/minio/creatives/

# Or use mc admin backup for full metadata
mc admin backup <ALIAS> --output /backups/minio/
```

**Status:** ❌ Not configured.

---

## 4. Redis Backup Decision

| Option | Recommendation |
|---|---|
| AOF persistence | ✅ Enable for durability |
| RDB snapshots | ⚠️ Daily, acceptable data loss |
| **Recommendation:** AOF enabled, RDB daily. Session data tolerate loss (re-login). | |

**Status:** ⬜ Not configured.

---

## 5. Config Backup

```bash
# Git-tracked configs
cp .env.production /backups/config/env.$(date +%Y%m%d)
cp infra/docker-compose.yml /backups/config/
cp alembic.ini /backups/config/

# Or just maintain a git repo of all config
# (ensure no secrets committed!)
```

**Status:** ⬜ Configs not backed up.

---

## 6. RPO / RTO (Placeholder — Define with Business)

| Service | RPO | RTO |
|---|---|---|
| PostgreSQL | TBD (target: 1h) | TBD (target: 30 min) |
| MinIO (creatives) | TBD (target: 24h) | TBD (target: 2h) |
| Redis (sessions) | TBD (target: 24h) | TBD (target: 30 min) |

---

## 7. Verification Steps (Post-Restore)

| Check | Method |
|---|---|
| DB accessible | `psql -c "SELECT 1"` |
| Tables exist | `psql -c "\dt" | wc -l` >= expected |
| Roles exist | `SELECT COUNT(*) FROM roles` |
| Seed idempotent | Run seeder: no errors |
| Backend health | `curl /health` |
| API functional | Smoke test suite |
| Portal functional | Smoke test suite |
| Manifest preview works | Gateway endpoint |
| Analytics data present | Run query |
| Emergency API works | Capabilities endpoint |

---

## 8. Failure Handling

| Failure | Action |
|---|---|
| pg_dump fails | Alert ops, retry within 1h |
| Disk full during backup | Alert, expand volume |
| Restore fails | Use previous day's backup |
| WAL corruption | Alert, fallback to full backup |
| MinIO backup fails | Retry, alert after 3 failures |
