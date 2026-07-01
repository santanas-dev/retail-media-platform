# Deployment Readiness Checklist

**Date:** 2026-07-02 | **Phase:** H.3 | **Owner:** Ops (TBD)

> **Status:** ⬜ PARTIAL — checklist exists, automation pending.  
> **IMPORTANT:** Production switch is NO-GO. KSO production switch is NO-GO.

---

## 1. Environment Matrix

| Environment | Alias | Host | Deploy Method | Approval Required |
|---|---|---|---|---|
| Local | local | developer machine | Manual / docker compose | No |
| Dev | dev | TBD | Manual / script | No |
| Stage | stage | TBD | Script (deploy_preflight + smoke) | Yes |
| **Prod** | **prod** | **TBD** | **Script + approval gate** | **Yes (formal)** |

---

## 2. Pre-Deploy Checks

| # | Check | Script | Status |
|---|---|---|---|
| P1 | Git status clean | `deploy_preflight.sh` | Manual |
| P2 | Target commit/tag verified | `deploy_preflight.sh` | Manual |
| P3 | All tests pass | pytest | Manual |
| P4 | Database migration check | `alembic current` | Manual |
| P5 | Required commands available | `deploy_preflight.sh` | Auto |
| P6 | PostgreSQL reachable | `deploy_preflight.sh` | Auto |
| P7 | Approval recorded | Manual (Jira/ticket) | Manual |

---

## 3. Deployment Steps (Placeholder)

```
1. APPROVAL: ticket/deploy-request approved by <APPROVER>
2. PRECHECK: bash scripts/ops/deploy_preflight.sh
3. BACKUP:  bash scripts/ops/backup_postgres.sh
4. DEPLOY:  docker compose -f infra/docker-compose.yml up -d
5. MIGRATE: alembic upgrade head
6. SEED:    python -m app.domains.identity.seed
7. SMOKE:   bash scripts/ops/post_deploy_smoke.sh
8. VERIFY:  Check Grafana (when available), portal, analytics
```

---

## 4. Post-Deploy Validation

| # | Check | Method |
|---|---|---|
| V1 | Backend /api/health/live → 200 | Smoke script |
| V2 | Backend /api/health/ready → 200 | Smoke script |
| V3 | Metrics endpoint → 200 | Smoke script |
| V4 | Emergency API → 401 | Smoke script |
| V5 | Portal health → 200 | Manual/script |
| V6 | Dashboard loads | Manual |
| V7 | Analytics shows data | Manual |
| V8 | Device heartbeat visible | Device dashboard |
| V9 | No new errors in logs | Log check |

---

## 5. Rollback Decision Point

After deployment, wait 5 minutes and verify:
- [ ] All smoke tests pass
- [ ] No error spike in logs
- [ ] Device heartbeats normal
- [ ] PoP events flowing

If ANY check fails — initiate rollback: `bash scripts/ops/rollback_preflight.sh`

---

## 6. Audit / Evidence

| Item | Method |
|---|---|
| Deploy log | Copy terminal output to deploy log |
| Commit deployed | `git log -1` |
| Smoke results | Copy smoke output |
| Approval reference | Link to ticket/Jira |
| Backup taken | Backup filename + size |

---

## 7. NO-GO Items

- ❌ KSO production switch
- ❌ ClickHouse enable
- ❌ Real emergency execution
- ❌ Production publish switch without approval
