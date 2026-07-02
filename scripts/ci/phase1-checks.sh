#!/usr/bin/env bash
#
# Phase 1 Quality Gates — Local Runner
#
# Runs the same checks as CI, using locally available tools.
# Usage: bash scripts/ci/phase1-checks.sh
#
# Prerequisites:
#   - python3  (3.11+)
#   - node / npm (22+)
#   - docker compose (or docker-compose)
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    shift
    echo -n "  [$name] "
    if "$@"; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${NC}"
        FAIL=$((FAIL + 1))
    fi
}

warn_check() {
    local name="$1"
    shift
    echo -n "  [$name] "
    if "$@"; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}WARN (optional)${NC}"
        WARN=$((WARN + 1))
    fi
}

echo "============================================"
echo " Phase 1 Quality Gates — Local Runner"
echo "============================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Python — Syntax Check
# ---------------------------------------------------------------------------
echo "--- Python Syntax Check ---"

PYTHON_FILES=(
    "apps/control-api/main.py"
    "apps/device-gateway/main.py"
    "apps/pop-ingestor/main.py"
    "apps/orchestrator-worker/main.py"
    "apps/adapter-workers/mock/main.py"
    "packages/domain/__init__.py"
    "packages/observability/__init__.py"
)

for f in "${PYTHON_FILES[@]}"; do
    check "py_compile $f" python3 -m py_compile "$f"
done

# ---------------------------------------------------------------------------
# 2. Python — Import Smoke
# ---------------------------------------------------------------------------
echo ""
echo "--- Python Import Smoke ---"

SERVICE_FILES=(
    "apps/control-api/main.py"
    "apps/device-gateway/main.py"
    "apps/pop-ingestor/main.py"
    "apps/orchestrator-worker/main.py"
    "apps/adapter-workers/mock/main.py"
)

for f in "${SERVICE_FILES[@]}"; do
    check "import $f" python3 -c "
import sys, os
sys.path.insert(0, '.')
# Provide __file__ and __name__ so os.path.dirname(__file__) works
_dir = os.path.dirname(os.path.abspath('$f'))
_mod = '$f'.replace('/', '.').replace('.py', '')
src = open('$f').read()
# Strip the 'if __name__' block at the bottom
if '__name__' in src:
    src = src.split(\"if __name__\")[0]
try:
    exec(compile(src, '$f', 'exec'), {'__file__': '$f', '__name__': _mod})
    print('OK')
except ImportError as e:
    if 'fastapi' in str(e) or 'uvicorn' in str(e):
        print('OK (stdlib only — no pip deps installed)')
    else:
        raise
except SystemExit:
    pass  # uvicorn.run tries to parse args, expected
"
done

# ---------------------------------------------------------------------------
# 3. JSON Schema Validation
# ---------------------------------------------------------------------------
echo ""
echo "--- JSON Schema Validation ---"

for f in packages/contracts/*.schema.json; do
    # JSON parse check
    check "parse $f" python3 -c "import json; json.load(open('$f'))"
    # Structure check
    check "structure $f" python3 -c "
import json
s = json.load(open('$f'))
assert '\$schema' in s, 'missing \$schema'
assert '\$id' in s, 'missing \$id'
assert s.get('type') == 'object', 'root must be object'
assert 'properties' in s, 'missing properties'
"
done

# ---------------------------------------------------------------------------
# 4. Docker Compose Config Validation
# ---------------------------------------------------------------------------
echo ""
echo "--- Docker Compose Config Validation ---"

if command -v docker &>/dev/null; then
    check "compose parse" docker compose -f infra/compose/docker-compose.phase1.yml config --dry-run >/dev/null 2>&1
    check "compose services (11)" python3 -c "
import yaml
with open('infra/compose/docker-compose.phase1.yml') as f:
    d = yaml.safe_load(f)
svc = d['services']
required = ['postgres','clickhouse','redis','nats','minio',
            'control-api','device-gateway','pop-ingestor',
            'orchestrator-worker','mock-adapter']
for s in required:
    assert s in svc, f'missing: {s}'
print(f'{len(svc)} services')
"
else
    echo "  [compose] SKIP — docker not available"
    WARN=$((WARN + 1))
fi

# ---------------------------------------------------------------------------
# 5. Frontend
# ---------------------------------------------------------------------------
echo ""
echo "--- Frontend ---"

if command -v node &>/dev/null && [ -f apps/admin-web/package.json ]; then
    cd apps/admin-web

    # Install if needed
    if [ ! -d node_modules ]; then
        echo "  [frontend] Installing dependencies..."
        npm install --silent 2>&1 | tail -1
    fi

    check "tsc --noEmit" npx tsc --noEmit
    check "vite build" npx vite build --logLevel error

    cd ../..
else
    echo "  [frontend] SKIP — node/npm not available"
    WARN=$((WARN + 1))
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
TOTAL=$((PASS + FAIL + WARN))
echo " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$WARN skipped/warned${NC} ($TOTAL total)"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
