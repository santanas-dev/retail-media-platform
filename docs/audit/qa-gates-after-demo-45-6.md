# QA Gates After Demo — 45.6

## Automated Checks

Run: `python3 qa_gates.py` from `apps/portal-web/`

### Gates

| # | Gate | Check |
|---|------|-------|
| 1 | Double-slash actions | `action="/...//"` or `href="/...//"` |
| 2 | Raw JSON errors | Traceback/TypeError/KeyError in templates |
| 3 | JS/CDN/localStorage | `<script>`, `onerror`, `onclick`, `cdn.jsdelivr`, `localStorage` |
| 4 | Broken images | `<img src="">` |
| 5 | Seed/test patterns | `test-kso`, `seed-`, `None`, `null`, `undefined` in templates |

### Manual Checks

| # | Gate | Method |
|---|------|--------|
| 6 | No 404/500 from visible actions | Click audit |
| 7 | No technical terms | Visual scan |
| 8 | Two-user E2E | maker-checker walkthrough |
| 9 | Regression | `python3 -m unittest discover` |

### Baseline

- Portal regression: 803 passed, 32 skipped
- Backend regression: 841 passed
- Last verified: commit e17900e (v0.9.0-rc0-business-demo.6)

### Change Log

- 45.6: QA gates script added, zero violations
