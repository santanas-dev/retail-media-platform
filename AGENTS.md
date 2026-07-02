# Retail Media Platform Agent Contract

This repository is built with AI assistance. Follow this contract before any
code change. The goal is a stable retail media product, not a pile of generated
features.

## Current Priority

Stabilization comes before new functionality.

## Source Of Truth

Before any architecture, planning, or implementation work, read:

1. `docs/00-source-of-truth/README.md`
2. `docs/00-source-of-truth/TZ_Retail_Media_Platform_v2_5_Final_Hermes.extracted.md`
3. `docs/00-source-of-truth/rmp_rewrite_starting_decisions.md`
4. `docs/00-source-of-truth/rmp_enterprise_architecture_review.md`
5. relevant ADRs/contracts in `docs/architecture/`

The source-of-truth folder overrides older generated phase reports unless a
newer approved ADR explicitly changes a decision. The original `.docx` in that
folder is traceability-only; agents should use the markdown extraction.

Fix critical platform risks first:

- PostgreSQL readiness must be real, not optimistic.
- Admin audit events must use valid actor UUIDs.
- Alembic configuration must use valid URLs and load model metadata.
- Production secrets, CORS, portal sessions, and rate limiting must be hardened.
- Portal/backend RBAC must not drift.

Do not start Android TV, ESL, LED, mobile, or broad UI redesign work until the
stabilization backlog is green or the user explicitly overrides this.

## Required Workflow

For every task:

1. Restate the exact task and scope.
2. Inspect existing code before proposing changes.
3. Name the domain boundary being touched.
4. Make the smallest coherent change.
5. Add or update targeted tests for the changed behavior.
6. Run the narrowest relevant tests first, then broader checks if risk warrants it.
7. Report changed files, verification results, and remaining risks honestly.

For new features, write a mini-design first and wait for explicit approval.
For bug fixes, do root-cause analysis first and include the failing condition in
the test or verification.

## Required Hermes Skills

Load these skills for this project work:

- `retail-media-platform`
- `critical-assessment`
- `systematic-debugging` for bugs, regressions, failing tests, runtime issues
- `project-audit` for audits and stabilization
- `retail-media-platform-backend` for backend changes
- `retail-media-platform-portal` and `portal-qa-testing` for portal changes
- `backend-api-hardening` for auth, RBAC, RLS, safe projection, audit, or API work

Do not use offensive/security-hunt skills for normal product development unless
the user explicitly asks for a security test or pentest task.

## Hermes Memory Rules

Use Hermes memory only for durable project facts:

- architecture decisions and approved product constraints;
- stable commands, ports, paths, and operational pitfalls;
- current stabilization priorities and verified baseline facts.

Never store API keys, tokens, passwords, cookies, raw customer data, temporary
logs, or unverified test counts in `MEMORY.md` or `USER.md`. Credentials belong
in protected environment files or secret storage. If a memory fact becomes
wrong, replace it instead of adding a contradictory entry.

## Protected Boundaries

Do not change these without explicit approval:

- `.env`, `.env.example`, production secrets, local credentials
- Docker, deployment, backup, and rollback scripts
- destructive migrations, `DROP`, `TRUNCATE`, broad `DELETE`
- campaign submit/approval/publication flows
- generated manifest compatibility
- device authentication and KSO runtime contracts
- large portal rewrites or broad CSS redesign

If a fix seems to require touching a protected boundary, stop and explain why.

## Architecture Rules

- Keep core channel-agnostic. KSO is the first channel, not the architecture.
- Routers validate and authorize; services own business logic.
- Permissions use backend permission codes, not role names.
- RLS/scope checks must use the authenticated user, not an unused `_` dependency.
- Device-facing APIs must not expose internal IDs, storage keys, paths, tokens, or secrets.
- Portal pages must use backend data or clearly marked safe demo data.
- Portal route guards must match backend permissions.
- Prefer existing domain modules over new parallel models.

## Editing Rules

- Prefer targeted patches over full file rewrites, especially for large files.
- Do not rewrite `apps/portal-web/main.py` wholesale.
- Do not create duplicate helpers if an equivalent local helper exists.
- Keep comments rare and useful.
- Preserve unrelated user changes.
- Never claim a baseline is green without running or inspecting it.

## Verification Rules

Minimum checks by area:

- Backend config/DB: import/config test, readiness test, affected unit tests.
- Auth/RBAC/audit: negative permission test and audit integrity check.
- Alembic: migration URL sanity and metadata/model import check.
- Portal: template/source inspection plus route/RBAC smoke where possible.
- Device/KSO: contract tests and no-secrets/no-path projection checks.

If dependencies or infrastructure are unavailable, say exactly what was not run
and provide the closest static or targeted verification.

## Reporting

Final reports must be short but concrete:

- what changed;
- files changed;
- commands/checks run;
- what remains risky.

Never write "all tests pass" unless they were actually run.
