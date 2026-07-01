#!/usr/bin/env bash
# Retail Media Platform — PostgreSQL restore script
# DESTRUCTIVE: overwrites target database.
# Usage: PGHOST=... PGDATABASE=... BACKUP_FILE=... CONFIRM_RESTORE=yes bash restore_postgres.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]] || [[ "${2:-}" == "--help" ]]; then
    echo "Usage: PGHOST=... PGDATABASE=... PGPASSWORD=*** PGUSER=... BACKUP_FILE=... CONFIRM_RESTORE=yes bash restore_postgres.sh [--dry-run]"
    echo "  --dry-run   Print what would be done without executing"
    echo "  --help      This message"
    echo ""
    echo "WARNING: DESTRUCTIVE — drops and recreates the database."
    echo "Requires CONFIRM_RESTORE=yes for non-dry-run execution."
    exit 0
fi

if $DRY_RUN; then
    echo "[DRY-RUN] Would restore ${BACKUP_FILE:-<BACKUP_FILE>} to ${PGDATABASE:-<PGDATABASE>}"
    echo "[DRY-RUN] Steps: dropdb → createdb → pg_restore"
    exit 0
fi

# Safety: require explicit confirmation
if [[ "${CONFIRM_RESTORE:-}" != "yes" ]]; then
    echo "ERROR: CONFIRM_RESTORE must be set to 'yes' for non-dry-run execution."
    echo "This is a DESTRUCTIVE operation — it drops and recreates the database."
    exit 1
fi

: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "WARNING: Restoring ${PGDATABASE} from ${BACKUP_FILE} — this will DROP and RECREATE the database."
echo "Press Ctrl+C within 5 seconds to abort..."
sleep 5

echo "Dropping ${PGDATABASE}..."
dropdb -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" "${PGDATABASE}"

echo "Creating ${PGDATABASE}..."
createdb -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" "${PGDATABASE}"

echo "Restoring from ${BACKUP_FILE}..."
pg_restore \
    -h "${PGHOST}" \
    -p "${PGPORT:-5432}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    --no-password \
    --clean \
    --if-exists \
    "${BACKUP_FILE}"

echo "Restore complete."
echo "Run migrations: alembic upgrade head"
echo "Run seed: python -m app.domains.identity.seed"
echo "Verify: curl <BACKEND_URL>/api/health/ready"
