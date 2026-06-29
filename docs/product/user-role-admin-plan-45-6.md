# User/Role Admin UI — Analysis & Plan (45.6)

## Current State

Portal has `/admin` route (RBAC-guarded: `users.read`, `roles.read`). 
Backend has 47 permissions, 8 roles, full RBAC/RLS enforcement.
User management currently only via backend API — no portal UI.

## Plan

### Phase 1: User Management UI (minimal)

1. **User list** — `/admin/users`
   - Table: username, display_name, roles, is_active, created_at
   - Server-side rendered, no JS
   - RBAC: `users.read`

2. **Create user** — form on `/admin/users`
   - Fields: username, display_name, password, roles (checkboxes from available roles)
   - RBAC: `users.create`
   - Password policy: min 8 chars

3. **Block/unblock user** — POST action
   - Toggle `is_active` flag
   - RBAC: `users.manage`
   - Audit trail: who blocked whom, when

4. **Assign roles** — POST action per user
   - Multi-select dropdown of available roles
   - RBAC: `roles.assign`
   - Validates role existence, prevents self-demotion

### Phase 2: Role Management

5. **Role list** — `/admin/roles`
   - Table: role code, label, permission count
   - RBAC: `roles.read`

6. **Role detail** — `/admin/roles/{code}`
   - Shows all permissions assigned to role
   - RBAC: `roles.read`

### Phase 3: RLS Scope Management

7. **Scope assignment** — per-user RLS scope (org, region, store group)
   - Dropdown from available scopes
   - RBAC: `admin.manage`
   - Never weakens existing RLS — additive only

### Phase 4: Audit Trail

8. **Audit viewer** — `/admin/audit`
   - Filterable by: user, action, date range, object type
   - Server-side rendering
   - No raw UUIDs, no technical codes in UI
   - RBAC: `audit.read`

### Safety Constraints
- Never expose raw UUIDs, password hashes, or tokens in UI
- Maker-checker preserved: admin cannot approve own role changes
- RBAC/RLS never weakened
- All changes logged to audit trail
