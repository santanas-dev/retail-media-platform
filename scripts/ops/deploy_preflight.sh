#!/usr/bin/env bash
# Retail Media Platform — Deploy preflight checks
# Safe: read-only, no mutations, no credentials printed.
# Usage: bash deploy_preflight.sh [--dry-run] [--help]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage: bash deploy_preflight.sh [--dry-run]"
    echo "  --dry-run   Print what would be checked without executing"
    echo "  --help      This message"
    exit 0
fi

ERRORS=0

check() {
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

echo "=== Deploy Preflight ==="
echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo ""

echo "--- Git ---"
check "git status clean" git diff-index --quiet HEAD -- 2>/dev/null || true

echo ""
echo "--- Required Commands ---"
for cmd in git python3 docker curl; do
    check "${cmd} available" command -v "${cmd}" &>/dev/null
done

echo ""
echo "--- Environment ---"
check "PGHOST set" bash -c '[[ -n "${PGHOST:-}" ]]'
check "BACKEND_BASE_URL set" bash -c '[[ -n "${BACKEND_BASE_URL:-}" ]]'

echo ""
echo "--- Database ---"
if [[ -n "${PGHOST:-}" ]]; then
    check "PostgreSQL reachable" bash -c "pg_isready -h '${PGHOST}' -p '${PGPORT:-5432}' -U '${PGUSER:-postgres}' &>/dev/null"
fi

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    echo "❌ ${ERRORS} preflight check(s) failed. Fix before deploying."
    exit 1
fi

echo ""
echo "✅ All preflight checks passed."
