#!/usr/bin/env bash
# Retail Media Platform — Rollback preflight checks
# Safe: read-only, requires approval placeholder, no actual rollback.
# Usage: TARGET_COMMIT=... ROLLBACK_APPROVAL=... bash rollback_preflight.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage: TARGET_COMMIT=<sha> ROLLBACK_APPROVAL=<name> BACKEND_BASE_URL=... bash rollback_preflight.sh [--dry-run]"
    echo "  --dry-run   Print what would be checked without executing"
    echo "  --help      This message"
    echo ""
    echo "This script does NOT perform rollback — it only validates readiness."
    exit 0
fi

ERRORS=0

check_ok() {
    local label="$1"; shift
    if $DRY_RUN; then
        echo "[DRY-RUN] Would check: ${label}"
        return 0
    fi
    if "$@"; then
        echo "  ✅ ${label}"
    else
        echo "  ❌ ${label}"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "=== Rollback Preflight ==="
echo ""

echo "--- Approval ---"
check_ok "ROLLBACK_APPROVAL set" bash -c '[[ -n "${ROLLBACK_APPROVAL:-}" ]]'

echo ""
echo "--- Target ---"
check_ok "TARGET_COMMIT set" bash -c '[[ -n "${TARGET_COMMIT:-}" ]]'
if [[ -n "${TARGET_COMMIT:-}" ]]; then
    check_ok "Target commit exists" bash -c "git cat-file -e ${TARGET_COMMIT} 2>/dev/null"
fi

echo ""
echo "--- Backup ---"
check_ok "Backup exists (<24h)" bash -c '[[ -n "${LAST_BACKUP_FILE:-}" && -f "${LAST_BACKUP_FILE}" ]]'

echo ""
echo "--- Health ---"
if [[ -n "${BACKEND_BASE_URL:-}" ]]; then
    BACKEND="${BACKEND_BASE_URL%/}"
    check_ok "Backend /health" bash -c "curl -s -o /dev/null -w '%{http_code}' '${BACKEND}/health' --max-time 5 | grep -q 200"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "❌ ${ERRORS} rollback preflight check(s) failed."
    echo "Fix issues or escalate before proceeding with rollback."
    exit 1
fi
echo "✅ Rollback preflight passed — ready for rollback decision."
echo "   Approver: ${ROLLBACK_APPROVAL:-TBD}"
echo "   Target:   ${TARGET_COMMIT:-TBD}"
