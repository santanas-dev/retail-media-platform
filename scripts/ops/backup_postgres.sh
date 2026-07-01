#!/usr/bin/env bash
# Retail Media Platform — PostgreSQL backup script
# Usage: PGHOST=... PGDATABASE=... BACKUP_DIR=... bash backup_postgres.sh [--dry-run] [--help]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]] || [[ "${2:-}" == "--help" ]]; then
    echo "Usage: PGHOST=... PGDATABASE=... PGUSER=... PGPASSWORD=... BACKUP_DIR=... bash backup_postgres.sh [--dry-run]"
    echo "  --dry-run   Print what would be done without executing"
    echo "  --help      This message"
    exit 0
fi

# Required env vars
: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"

OUTPUT_FILE="${BACKUP_DIR}/retail_media_$(date +%Y%m%d_%H%M%S).dump"

if $DRY_RUN; then
    echo "[DRY-RUN] Would backup ${PGDATABASE} to ${OUTPUT_FILE}"
    echo "[DRY-RUN] Command: pg_dump -h <HOST> -U <USER> -d ${PGDATABASE} --format=custom -f ${OUTPUT_FILE}"
    exit 0
fi

mkdir -p "${BACKUP_DIR}"

echo "Backing up ${PGDATABASE} to ${OUTPUT_FILE}..."
# PGPASSWORD is passed via env (never printed)
if [[ -z "${PGPASSWORD:-}" ]]; then
    echo "ERROR: PGPASSWORD is empty or unset"
    exit 1
fi
PGPASSWORD="${PGPASSWORD}" pg_dump \
    -h "${PGHOST}" \
    -p "${PGPORT:-5432}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    --format=custom \
    --no-password \
    -f "${OUTPUT_FILE}"

echo "Backup complete: ${OUTPUT_FILE} (size: $(du -h "${OUTPUT_FILE}" | cut -f1))"
