# Hermes Agent Operating Model for Retail Media Platform

## Purpose

Hermes with DeepSeek 4 Pro should act as an implementation worker under a
strict product and architecture contract. It should not independently expand
scope, invent new architecture, or chase broad redesigns before stabilizing the
platform.

## Recommended Roles

Use this split even if all work is done by one Hermes instance:

- **Planner:** turns user requests into scoped tasks and mini-designs.
- **Builder:** implements only the approved task.
- **Reviewer:** checks architecture, RBAC/RLS, tests, and protected boundaries.
- **QA:** runs targeted tests, browser checks, and honest baseline reports.

For small tasks, Hermes may do all roles sequentially. It must still report
which role it is performing.

## Default Task Template

Use this prompt shape for Hermes:

```text
Project: Retail Media Platform.
Load skills: retail-media-platform, critical-assessment, systematic-debugging.

Task:
<one exact task>

Scope:
- Allowed files:
  - <file/path>
- Forbidden changes:
  - no Docker/.env/deployment changes
  - no unrelated refactors
  - no broad portal rewrite

Required process:
1. Inspect the relevant code first.
2. Explain root cause or mini-design.
3. Make the smallest patch.
4. Add/update targeted tests.
5. Run targeted verification.
6. Report changed files and remaining risks.

Acceptance:
- <observable behavior>
- <test command or static verification>
```

## Stabilization Backlog

Run this before feature work:

1. Fix real PostgreSQL readiness and `/api/health/ready`.
2. Fix admin audit actor handling so create/role operations cannot fail after commit.
3. Fix Alembic sync/offline URL and load metadata for all models.
4. Harden secret validation for placeholder `SECRET_KEY` and initial admin password.
5. Move CORS origins to environment configuration.
6. Replace or constrain in-memory rate limiting for production and stop trusting raw `X-Forwarded-For`.
7. Make portal session security environment-aware and production-safe.
8. Align portal cached RBAC with backend permission changes.
9. Add tests for these fixes.
10. Update docs only after behavior is verified.

## Hermes Configuration Recommendations

Current useful settings:

- DeepSeek v4 Pro as default model is fine for implementation.
- Manual approvals are good.
- `file_mutation_verifier` is good.
- Persistent shell is useful for the project.

Recommended changes:

- Enable hard loop stops: `tool_loop_guardrails.hard_stop_enabled: true`.
- Keep built-in memory as the default provider unless semantic cross-project
  recall becomes necessary.
- Enable privacy redaction: `privacy.redact_pii: true`.
- Keep secret redaction enabled: `security.redact_secrets: true`.
- Use moderate memory limits for RMP context:
  - `memory.memory_char_limit: 6000`;
  - `memory.user_char_limit: 3000`;
  - `memory.flush_min_turns: 4`;
  - `memory.nudge_interval: 8`.
- Keep `max_turns` high, but require task-level scope in prompts.
- Do not enable offensive/hunt skills globally for product work.
- Prefer a dedicated RMP profile if Hermes supports profiles:
  - enabled skills: RMP, backend, portal, audit, systematic debugging, QA;
  - disabled or avoided skills: bug bounty, red team, OSINT, cloud attack, exploit hunting;
  - default cwd: `/home/cobalt/retail-media-platform`.

## Memory Hygiene

Hermes memory should stay small, factual, and project-safe.

Remember:

- approved architecture decisions and product constraints;
- stable commands, ports, paths, and runtime traps;
- verified baseline facts with dates or commits when they can drift;
- current stabilization priorities.

Do not remember:

- API keys, tokens, passwords, cookies, or one-time credentials;
- raw customer data, logs, screenshots with private data, or Telegram secrets;
- temporary test failures unless they are tied to a durable known issue;
- generated metrics or counts unless Hermes has verified them in the repo.

When a fact becomes wrong, replace or remove it. Do not add a second competing
memory entry.

## Review Checklist

Before accepting Hermes output, check:

- Did it inspect code before editing?
- Did it touch only allowed files?
- Did it create a duplicate model/helper/flow?
- Did it use permission codes rather than role names?
- Did it preserve channel-agnostic architecture?
- Did it add a test or a credible verification?
- Did it honestly report failed/skipped tests?
- Did it leave the git tree understandable?

## Stop Conditions

Stop Hermes and ask for human review if:

- it proposes broad rewrites;
- it touches `.env`, Docker, deployment, or destructive migrations;
- it says tests pass without showing commands;
- it changes publication/KSO/device-auth contracts without a mini-design;
- it repeats the same failed fix twice;
- it starts implementing a new channel before stabilization is complete.
