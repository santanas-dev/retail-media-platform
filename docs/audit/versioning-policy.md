# Versioning Policy

> **Project:** Retail Media Platform  
> **Scheme:** SemVer (`MAJOR.MINOR.PATCH-descriptor`)  
> **Last updated:** 2026-06-26 (38.8.1)

---

## Version Scheme

```
v<MAJOR>.<MINOR>.<PATCH>-<descriptor>
```

| Component | Meaning | When to bump | Example |
|---|---|---|---|
| **MAJOR** | Production-level milestone | Pilot rollout, breaking changes, first production release | `v1.0.0` |
| **MINOR** | Completed project phase | New feature group, new domain, phase completion | `v0.5.0` |
| **PATCH** | Small fixes/docs | Regression update, doc-only change, typo fix | `v0.5.1` |
| **descriptor** | Short human-readable name | Every tag — describes the milestone | `test-kso-phase-a-readiness` |

---

## Tag Requirements (every MINOR tag)

### Mandatory

1. ✅ **Green full regression** — all 6 suites pass (Backend, Portal, State, Player, Sidecar, Infra)
2. ✅ **Clean git status** — `git status --short` returns empty
3. ✅ **No secrets** — no real URLs, tokens, `device_secret`, passwords in:
   - Docs (`docs/audit/*.md`)
   - CHANGELOG
   - Tag message
   - Any committed file
4. ✅ **Annotated tag** — `git tag -a` with meaningful description
5. ✅ **CHANGELOG entry** — section with date, key changes, regression results, exclusions

### Recommended

- ✅ Portal `/readiness` shows consistent status
- ✅ Backend seed idempotent
- ✅ Phase D gate correctly blocked (if pre-production)

---

## Git Tag Commands

### Create current milestone tag

```bash
git tag -a v0.5.0-test-kso-phase-a-readiness -m "v0.5.0 Test KSO Phase A readiness"
```

### List all tags

```bash
git tag -l -n
```

### Push tags to remote

```bash
git push --tags
```

### Checkout by tag (read-only inspection)

```bash
git checkout v0.5.0-test-kso-phase-a-readiness
# … inspect, then return to main:
git checkout main
```

---

## Retrospective Tags

Tags for past milestones (v0.1.0–v0.4.0) have **not** been created. Retrospective tags require explicit confirmation before creation, because:

- The commits they would point to may have known issues
- Full regression may not have existed at those points
- Backend URL / secret hygiene may not have been enforced

If needed, propose a list first — do **not** create retrospective tags without approval.

---

## Current Tags

| Tag | Commit | Date | Description |
|---|---|---|---|
| `v0.6.0-sidecar-config-readiness` | (current) | 2026-06-26 | Sidecar config template, validation, gitignore |
| `v0.5.0-test-kso-phase-a-readiness` | `87ab0be` | 2026-06-26 | Backend-only Phase A readiness verified |

---

## Future Tags (proposed)

| Tag | Expected content |
|---|---|
| `v0.7.0-one-kso-e2e-dry-run` | Controlled one-KSO E2E dry run (Phase C+D, non-production) |
| `v0.8.0-pilot-readiness` | All prerequisites met — pilot rollout gate open |
| `v1.0.0-kso-production-release` | First production KSO release |

---

## Anti-Patterns

- ❌ Tagging with dirty git status
- ❌ Tagging without running full regression
- ❌ Including real backend URL in tag message
- ❌ Including `device_secret` value in any committed file
- ❌ Lightweight tags for milestones (use `-a` for annotated)
- ❌ Retrospective tags without explicit confirmation
