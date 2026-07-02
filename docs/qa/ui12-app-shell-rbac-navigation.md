# UI.1.2 — App Shell / RBAC-aware Navigation

**Phase:** UI.1.2 | **Previous:** UI.1.1 (`67cc861`) | **Status:** ✅ GO for UI.1.3

---

## Changes

### base.html — rewritten with RBAC-aware nav
- **6 групп:** Продажи / Планирование / Публикация / Устройства / Аналитика / Администрирование + Сервис (public)
- **Permission mapping:** каждый nav-элемент показывается только при наличии соответствующего permission
- **Пустые группы:** скрываются
- **device_service:** видит только Устройства + Аналитика (если `reports.read`)
- **Active state:** по `active` переменной из контекста
- **User panel:** `.user-panel` с именем и ролями

### main.py — permissions во всех handlers
- `_page` helper: +`get_session_permissions(request)`
- Все inline handlers: +`"permissions": get_session_permissions(request)` (49 мест)
- Import `get_session_permissions` из `portal_session`

### styles.css — новые app shell классы
- `.sidebar-link`, `.sidebar-brand`, `.sidebar-section-title`
- `.user-panel`, `.user-name`, `.user-roles`
- `.main-content` (+ legacy `.main`)
- Responsive: `.sidebar-link` (768px icon-only)

## Tests: 38/38 ✅ | Regression: 1394/0 ✅
