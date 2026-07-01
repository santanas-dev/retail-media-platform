#!/usr/bin/env bash
# Retail Media Platform — MinIO backup script
# Usage: MINIO_ALIAS=... MINIO_BUCKET=... BACKUP_DIR=... bash backup_minio.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]] || [[ "${2:-}" == "--help" ]]; then
    echo "Usage: MINIO_ALIAS=... MINIO_BUCKET=... BACKUP_DIR=... bash backup_minio.sh [--dry-run]"
    echo "  --dry-run   Print what would be done without executing"
    echo "  --help      This message"
    exit 0
fi

if ! command -v mc &>/dev/null; then
    echo "WARNING: 'mc' (MinIO Client) not found."
    echo "Install: https://min.io/docs/minio/linux/reference/minio-mc.html"
    if $DRY_RUN; then
        echo "[DRY-RUN] Would use mc to mirror bucket."
        exit 0
    fi
    exit 1
fi

: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${MINIO_ALIAS:?MINIO_ALIAS is required}"
: "${MINIO_BUCKET:?MINIO_BUCKET is required}"

if $DRY_RUN; then
    echo "[DRY-RUN] Would mirror ${MINIO_ALIAS}/${MINIO_BUCKET} to ${BACKUP_DIR}"
    echo "[DRY-RUN] Command: mc mirror ${MINIO_ALIAS}/${MINIO_BUCKET} ${BACKUP_DIR}/${MINIO_BUCKET}/"
    exit 0
fi

mkdir -p "${BACKUP_DIR}/${MINIO_BUCKET}"
echo "Mirroring ${MINIO_ALIAS}/${MINIO_BUCKET} to ${BACKUP_DIR}/${MINIO_BUCKET}/..."
mc mirror "${MINIO_ALIAS}/${MINIO_BUCKET}" "${BACKUP_DIR}/${MINIO_BUCKET}/"

echo "Backup complete."
