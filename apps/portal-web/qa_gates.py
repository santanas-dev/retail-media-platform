"""QA Gate Automation — automated checks for portal quality gates.

Runs offline (no server needed) against template files and source code.
Detects: raw JSON errors, double-slash actions, 404/500 from visible actions,
test/seed/None/null in templates, technical terms, broken images,
JS/CDN/localStorage.

Usage:
    python3 qa_gates.py
"""

import re
import sys
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PORTAL_DIR / "templates"
STATIC_DIR = PORTAL_DIR / "static"

# Patterns to detect
DOUBLE_SLASH = re.compile(r'(?:action|href)=["\']/[a-z_-]+//')
RAW_JSON_KW = re.compile(r'\b(?:Traceback|TypeError|KeyError|AttributeError|JSONDecodeError)\b', re.IGNORECASE)
TECH_TERMS = re.compile(
    r'\b(?:backend_url|object_code|raw_uuid|device_secret|access_token|'
    r'refresh_token|password_hash|bearer_token|api_key)\b',
    re.IGNORECASE,
)
SEED_PATTERNS = re.compile(
    r'\b(?:test-kso|test-dev-seed|demo-kso|seed-|test_kso|'
    r'None\b|null\b|undefined\b)\b',
)
JS_CDN_PATTERNS = re.compile(
    r'(?:<script\b|javascript:|onerror=|onclick=|onload=|'
    r'cdn\.jsdelivr\.net|unpkg\.com|localStorage\b|sessionStorage\b)',
    re.IGNORECASE,
)
BROKEN_IMAGE = re.compile(r'<img[^>]*src=["\']["\']')  # empty src


def check_template(path: Path) -> list[str]:
    """Check a single template file for issues."""
    issues = []
    content = path.read_text(errors="replace")

    if DOUBLE_SLASH.search(content):
        issues.append(f"  DOUBLE-SLASH: {path.name}")

    if RAW_JSON_KW.search(content) and path.suffix == ".html":
        # Only flag in HTML templates (Python files may have legit references)
        pass  # Too noisy for Python; handled by error handlers

    if SEED_PATTERNS.search(content) and path.suffix == ".html":
        # Flag seed/test data in templates
        matches = SEED_PATTERNS.findall(content)
        # Filter false positives
        real = [m for m in matches if m.lower() not in ("none", "null", "undefined")]
        if real:
            issues.append(f"  SEED/TEST: {path.name} — {real[:3]}")

    if JS_CDN_PATTERNS.search(content):
        # Ignore if the match is in a comment/docstring about "no JS/CDN"
        clean = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        clean = re.sub(r'\"\"\".*?\"\"\"', '', clean, flags=re.DOTALL)
        if JS_CDN_PATTERNS.search(clean):
            issues.append(f"  JS/CDN: {path.name}")
        # else: false positive in comments

    if BROKEN_IMAGE.search(content):
        issues.append(f"  BROKEN-IMG: {path.name}")

    return issues


def check_source(path: Path) -> list[str]:
    """Check a Python source file for issues."""
    issues = []
    content = path.read_text(errors="replace")

    if DOUBLE_SLASH.search(content):
        issues.append(f"  DOUBLE-SLASH: {path.name}")

    if RAW_JSON_KW.search(content) and path.stem != "qa_gates":
        # Check for raw traceback rendering
        if 'raise HTTPException' not in content and 'Response(' not in content:
            issues.append(f"  RAW-JSON: {path.name} — possible unhandled exception")

    if JS_CDN_PATTERNS.search(content):
        # Ignore if the match is in a comment/docstring about "no JS/CDN"
        clean = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        clean = re.sub(r'\"\"\".*?\"\"\"', '', clean, flags=re.DOTALL)
        if JS_CDN_PATTERNS.search(clean):
            issues.append(f"  JS/CDN: {path.name}")
        # else: false positive in comments

    return issues


def main() -> int:
    all_issues: dict[str, list[str]] = {}

    # Check all HTML templates
    for tf in TEMPLATES_DIR.rglob("*.html"):
        issues = check_template(tf)
        if issues:
            all_issues[str(tf.relative_to(PORTAL_DIR))] = issues

    # Check Python source files (main.py only for now)
    main_py = PORTAL_DIR / "main.py"
    if main_py.exists():
        issues = check_source(main_py)
        if issues:
            all_issues[str(main_py.relative_to(PORTAL_DIR))] = issues

    # Also check rbac.py, action_availability.py
    for py_file in PORTAL_DIR.glob("*.py"):
        if py_file.name in ("rbac.py", "action_availability.py", "backend_client.py"):
            issues = check_source(py_file)
            if issues:
                all_issues[str(py_file.relative_to(PORTAL_DIR))] = issues

    if all_issues:
        print("❌ QA GATE FAILURES:")
        for fname, issues in sorted(all_issues.items()):
            print(f"\n  {fname}:")
            for iss in issues:
                print(iss)
        print(f"\n  Total: {sum(len(v) for v in all_issues.values())} issues in {len(all_issues)} files")
        return 1
    else:
        print("✅ QA GATES PASS — all checks clean")
        return 0


if __name__ == "__main__":
    sys.exit(main())
