# ADR-004: Frontend Stack — React + TypeScript

**Status:** Accepted
**Date:** 2026-07-02
**Phase:** 0 (Architecture Lock)
**Deciders:** Sergey Paschenko (project owner), Hermes Agent

## Context

ТЗ v2.5 §21.4 requires a `/frontend` directory with React + TypeScript as the recommended stack. The current Jinja2 SSR portal (`apps/portal-web/`) is a prototype and not suitable for enterprise admin workflows (§22.13: role-based UIs, saved filters, bulk actions, progress indicators).

The `rmp_rewrite_starting_decisions.md` confirms: React + TypeScript is approved for the rewrite. The current Jinja portal is reference/prototype only.

## Decision

**React + TypeScript with a restrained internal design system.**

### Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 19 | Approved by project owner; mature ecosystem |
| Language | TypeScript 5.x | Type safety for enterprise codebase |
| Build | Vite | Fast HMR, modern ESM, no Next.js overhead |
| Router | TanStack Router | Type-safe, file-based or code-based; or React Router v7 |
| Data fetching | TanStack Query | Cache, retry, optimistic updates, pagination |
| UI components | Internal design system (CSS Modules or Tailwind) | No external UI library dependency; enterprise restraint |
| Forms | React Hook Form + Zod | Type-safe validation matching backend Pydantic schemas |
| Table library | TanStack Table or custom | Pagination, sorting, filtering for admin tables |
| Charts | Recharts or custom SVG | Lightweight, no D3 complexity |
| Testing | Vitest + React Testing Library | Fast, compatible with Vite |
| Lint/format | Biome or ESLint + Prettier | Consistent code style |

### Two Separate Applications

| Portal | Route | Users | Auth |
|--------|-------|-------|------|
| **Admin Web** | `/apps/admin-web/` | Internal: admin, manager, approver, analyst, operator | AD/SSO + MFA |
| **Advertiser Web** | `/apps/advertiser-web/` | External: advertisers | AD/SSO or API-key; read-only |

### Design Principles

- **No external UI libraries** (no MUI, Ant Design, Chakra). Internal design system built on CSS Modules or Tailwind with design tokens.
- **Business-oriented, not marketing.** Clean tables, filters, dashboards. No gratuitous animations.
- **Accessibility:** keyboard navigation, focus management, semantic HTML.
- **SSR is NOT required.** SPA with API calls to Control API is sufficient for admin workflows. No Next.js unless SSR becomes a hard requirement.

### What Must NOT Be

- Jinja2 mixed with React (two separate applications)
- CDN-hosted dependencies in production
- localStorage for auth tokens (httpOnly cookies or memory only)
- Direct access to PostgreSQL/ClickHouse/MinIO from frontend code
- Unrestricted API access (RBAC enforced server-side, never client-side trust)

## Consequences

- **Positive:** Modern toolchain; type safety across API contracts; maintainable for multiple developers; separate advertiser portal avoids internal complexity leaking to external users.
- **Negative:** Two React apps to build and deploy; need API client generation or manual typing; frontend developers must learn TypeScript if not already familiar.
- **Risk:** React SPA may feel heavy for simple pages. Mitigation: code splitting, lazy loading, bundle analysis.

## References

- TZ v2.5 §21.4 (Required Project Structure), §22.13 (UX for Different Roles)
- `rmp_rewrite_starting_decisions.md` — Confirmed frontend stack
- `rmp_enterprise_architecture_review.md` — Technology Choices
