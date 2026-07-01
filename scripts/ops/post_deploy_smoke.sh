#!/usr/bin/env bash
# Retail Media Platform — Post-deploy smoke tests
# Safe: read-only health checks, no auth secrets in output.
# Usage: BACKEND_BASE_URL=... PORTAL_BASE_URL=... bash post_deploy_smoke.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=true; fi
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage: BACKEND_BASE_URL=... [PORTAL_BASE_URL=...] bash post_deploy_smoke.sh [--dry-run]"
    echo "  --dry-run   Print what would be checked without executing"
    echo "  --help      This message"
    exit 0
fi

ERRORS=0

smoke() {
    local label="$1" url="$2" expected_code="${3:-200}"
    if $DRY_RUN; then
        echo "[DRY-RUN] Would check: ${label} → ${url}"
        return 0
    fi
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null || echo "000")
    if [[ "${code}" == "${expected_code}" ]]; then
        echo "  ✅ ${label} (${code})"
    else
        echo "  ❌ ${label} (${code}, expected ${expected_code})"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "=== Post-Deploy Smoke ==="
echo ""

BACKEND="${BACKEND_BASE_URL:?BACKEND_BASE_URL is required}"
BACKEND="${BACKEND%/}"

smoke "Backend live"        "${BACKEND}/api/health/live"
smoke "Backend ready"       "${BACKEND}/api/health/ready"
smoke "Backend metrics"     "${BACKEND}/api/health/metrics"
smoke "Emergency API"       "${BACKEND}/api/emergency/capabilities" 401  # auth required = 401

if [[ -n "${PORTAL_BASE_URL:-}" ]]; then
    PORTAL="${PORTAL_BASE_URL%/}"
    smoke "Portal health"   "${PORTAL}/health"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "❌ ${ERRORS} smoke test(s) failed."
    exit 1
fi
echo "✅ All smoke tests passed."
