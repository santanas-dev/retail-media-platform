# Portal UX Hardening — 45.9

**Date:** 2026-06-29
**Baseline:** 5ed2c30
**Scope:** Form accessibility, navigation, density, empty states

## Changes

### Form Accessibility
| Page | Change |
|---|---|
| schedule.html | 6 labels added to slot form (Код слота, Размещение, День недели, Начало, Конец) |
| approvals.html | 1 label added (Причина отказа for reject comment) |
| campaigns_detail.html | Required marker added to schedule name label |
| admin.html | Required markers added to username/password labels (5 labels) |

### Cancel/Back Links
| Page | Change |
|---|---|
| schedule.html | "Отмена" link added to create schedule form |
| admin.html | "Отмена" links added to all 4 forms (create, block, archive, assign roles) |
| campaigns_detail.html | "Отмена" link added to create-schedule form |
| approvals.html | "Отмена" link added to create approval request form |

### Density
| Page | Change |
|---|---|
| admin.html | Quick-nav strip (Пользователи, Роли, Аудит) + id anchors added |

### Empty States
| Page | Change |
|---|---|
| inventory.html | CTA buttons added (Настроить расписания, Создать кампанию) |

### Tests
- 10 UX audit tests: labels, required markers, cancel links, empty states, no JS/CDN/localStorage, no raw JSON, no technical language
- All 10 pass

## Gates

| Gate | Status |
|---|---|
| Form labels | All visible inputs have labels ✅ |
| Required markers | All required fields marked ✅ |
| Cancel/back links | All forms have cancel/back ✅ |
| Empty states have CTA | inventory + stores ✅ |
| No JS/CDN/localStorage | 0 across all 22 pages ✅ |
| No raw JSON in templates | 0 ✅ |
| No technical words | 0 ✅ |
| No business logic changes | 0 backend files touched ✅ |
| RBAC/RLS unchanged | ✅ |
| Maker-checker unchanged | ✅ |
| Audit trail unchanged | ✅ |
