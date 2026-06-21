"""Security contract for Retail Media Platform — Auth, RBAC, RLS foundation.

This defines the architectural contract for authentication, role-based access
control (RBAC), and row-level security (RLS). No real auth is implemented —
this is a foundation document for backend enforcement.

IMPORTANT:
- UI hiding is NOT security. Backend/DB/API must enforce all rules.
- Manual URL opening must not bypass permissions.
- Excel export must apply the same RLS as reports.
- RLS scopes are additive — user sees the union of their scopes.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import FrozenSet


# ═══════════════════════════════════════════════════════════════════════
# Roles
# ═══════════════════════════════════════════════════════════════════════

class Role(Enum):
    """Platform roles — assigned via corporate identity provider (SSO/AD)."""
    SYSTEM_ADMIN = "system_admin"
    SECURITY_ADMIN = "security_admin"
    AD_MANAGER = "ad_manager"
    APPROVER = "approver"
    ANALYST = "analyst"
    ADVERTISER = "advertiser"
    OPERATIONS = "operations"
    DEVICE_SERVICE = "device_service"


ROLE_LABELS: dict[str, str] = {
    "system_admin": "Системный администратор",
    "security_admin": "Администратор безопасности",
    "ad_manager": "Менеджер рекламы",
    "approver": "Согласующий",
    "analyst": "Аналитик",
    "advertiser": "Рекламодатель",
    "operations": "Оператор",
    "device_service": "Сервис КСО",
}


# ═══════════════════════════════════════════════════════════════════════
# Permissions
# ═══════════════════════════════════════════════════════════════════════

class Permission(Enum):
    """Granular permissions — checked at API/backend level."""
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_STORES = "view_stores"
    VIEW_DEVICES = "view_devices"
    VIEW_CREATIVES = "view_creatives"
    VIEW_CAMPAIGNS = "view_campaigns"
    VIEW_SCHEDULE = "view_schedule"
    VIEW_PUBLICATIONS = "view_publications"
    VIEW_PROOF_OF_PLAY = "view_proof_of_play"
    VIEW_APPROVALS = "view_approvals"
    VIEW_REPORTS = "view_reports"
    VIEW_DEPLOYMENT = "view_deployment"
    VIEW_ADMIN = "view_admin"
    EXPORT_REPORTS = "export_reports"
    APPROVE_OBJECTS = "approve_objects"
    PUBLISH_MANIFEST = "publish_manifest"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    MANAGE_DEVICES = "manage_devices"
    VIEW_AUDIT = "view_audit"


# Role → Permissions mapping
ROLE_PERMISSIONS: dict[str, FrozenSet[str]] = {
    "system_admin": frozenset({
        "view_dashboard", "view_stores", "view_devices",
        "view_creatives", "view_campaigns", "view_schedule",
        "view_publications", "view_proof_of_play",
        "view_approvals", "view_reports",
        "view_deployment", "view_admin",
        "export_reports", "manage_users", "manage_roles",
        "manage_devices", "view_audit",
    }),
    "security_admin": frozenset({
        "view_dashboard", "view_admin",
        "manage_users", "manage_roles", "view_audit",
    }),
    "ad_manager": frozenset({
        "view_dashboard", "view_stores", "view_devices",
        "view_creatives", "view_campaigns", "view_schedule",
        "view_publications", "view_proof_of_play",
        "view_approvals", "view_reports",
        "view_deployment", "export_reports",
        "approve_objects", "publish_manifest",
    }),
    "approver": frozenset({
        "view_dashboard", "view_creatives", "view_campaigns",
        "view_schedule", "view_publications",
        "view_approvals", "view_reports",
        "approve_objects",
    }),
    "analyst": frozenset({
        "view_dashboard", "view_stores", "view_devices",
        "view_creatives", "view_campaigns", "view_schedule",
        "view_publications", "view_proof_of_play",
        "view_reports", "export_reports",
    }),
    "advertiser": frozenset({
        "view_dashboard", "view_creatives", "view_campaigns",
        "view_schedule", "view_publications",
        "view_proof_of_play", "view_reports",
    }),
    "operations": frozenset({
        "view_dashboard", "view_stores", "view_devices",
        "view_deployment", "manage_devices",
    }),
    "device_service": frozenset({
        "view_dashboard", "view_devices",
        "view_deployment", "manage_devices",
    }),
}


# ═══════════════════════════════════════════════════════════════════════
# RLS Scopes
# ═══════════════════════════════════════════════════════════════════════

class RLSScope(Enum):
    """Row-level security scopes — restrict data visibility."""
    ADVERTISER_SCOPE = "advertiser_scope"
    BRANCH_SCOPE = "branch_scope"
    STORE_SCOPE = "store_scope"
    CAMPAIGN_SCOPE = "campaign_scope"
    DEVICE_SCOPE = "device_scope"
    APPROVAL_SCOPE = "approval_scope"
    REPORT_SCOPE = "report_scope"


RLS_SCOPE_LABELS: dict[str, str] = {
    "advertiser_scope": "По рекламодателю — видит только свои кампании и креативы",
    "branch_scope": "По филиалу — видит только магазины своего филиала",
    "store_scope": "По магазину — видит только свои КСО и показы",
    "campaign_scope": "По кампании — видит только свои кампании",
    "device_scope": "По устройству — видит только свои КСО",
    "approval_scope": "По согласованию — видит только свои объекты согласования",
    "report_scope": "По отчётам — видит только агрегаты по своим scope",
}


# Role → RLS scopes (additive union)
ROLE_RLS_SCOPES: dict[str, FrozenSet[str]] = {
    "system_admin": frozenset(),
    "security_admin": frozenset(),
    "ad_manager": frozenset({
        "branch_scope", "store_scope", "campaign_scope",
        "device_scope", "approval_scope", "report_scope",
    }),
    "approver": frozenset({
        "campaign_scope", "approval_scope", "report_scope",
    }),
    "analyst": frozenset({
        "branch_scope", "store_scope", "campaign_scope",
        "device_scope", "report_scope",
    }),
    "advertiser": frozenset({
        "advertiser_scope", "campaign_scope", "report_scope",
    }),
    "operations": frozenset({
        "branch_scope", "store_scope", "device_scope",
    }),
    "device_service": frozenset({
        "store_scope", "device_scope",
    }),
}

# Empty frozenset = no RLS restriction (full access).
# system_admin and security_admin have no RLS — they see everything.


# ═══════════════════════════════════════════════════════════════════════
# Page Access Matrix
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PageAccess:
    """Defines which role/permission grants access to a portal page."""
    route: str
    title: str
    required_permission: str
    visible_to: FrozenSet[str] = field(default_factory=frozenset)


PAGE_ACCESS_MATRIX: tuple[PageAccess, ...] = (
    PageAccess("/dashboard", "Dashboard", "view_dashboard"),
    PageAccess("/campaigns", "Кампании", "view_campaigns"),
    PageAccess("/creatives", "Креативы", "view_creatives"),
    PageAccess("/schedule", "Расписание", "view_schedule"),
    PageAccess("/publications", "Публикации", "view_publications"),
    PageAccess("/stores", "Магазины", "view_stores"),
    PageAccess("/devices", "КСО Устройства", "view_devices"),
    PageAccess("/proof-of-play", "Proof of Play", "view_proof_of_play"),
    PageAccess("/approvals", "Согласования", "view_approvals"),
    PageAccess("/reports", "Отчёты", "view_reports"),
    PageAccess("/deployment", "Развёртывание", "view_deployment"),
    PageAccess("/admin", "Администрирование", "view_admin"),
)


# ═══════════════════════════════════════════════════════════════════════
# Security Principles
# ═══════════════════════════════════════════════════════════════════════

SECURITY_PRINCIPLES: tuple[str, ...] = (
    "UI hiding is NOT security. Backend/DB/API must enforce all rules.",
    "RLS must be enforced on backend/DB/API level.",
    "Excel export must apply the same RLS as reports.",
    "Manual URL opening must not bypass permissions.",
    "BI reports must apply RLS filters before aggregation.",
    "Approval workflow must enforce role-based routing.",
    "All access decisions are made server-side, never client-side.",
)


# ═══════════════════════════════════════════════════════════════════════
# Auth Modes
# ═══════════════════════════════════════════════════════════════════════

LOCAL_AUTH_SUPPORTED: bool = True
"""Portal supports local user accounts managed in Admin."""

SSO_AUTH_SUPPORTED: bool = True
"""Portal supports corporate SSO / Active Directory."""

LOCAL_USER_MANAGEMENT_REQUIRED: bool = True
"""Users must be creatable, editable, and manageable within the portal Admin UI."""


# ═══════════════════════════════════════════════════════════════════════
# User Statuses
# ═══════════════════════════════════════════════════════════════════════

class UserStatus(Enum):
    """User account lifecycle states."""
    ACTIVE = "active"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    PENDING_ACTIVATION = "pending_activation"


USER_STATUS_LABELS: dict[str, str] = {
    "active": "Активен",
    "blocked": "Заблокирован",
    "archived": "Архив",
    "pending_activation": "Ожидает активации",
}


# ═══════════════════════════════════════════════════════════════════════
# Admin Capabilities
# ═══════════════════════════════════════════════════════════════════════

class AdminCapability(Enum):
    """Capabilities available to security/system administrators."""
    CREATE_USER = "create_user"
    BLOCK_USER = "block_user"
    ARCHIVE_USER = "archive_user"
    ASSIGN_ROLES = "assign_roles"
    ASSIGN_RLS_SCOPES = "assign_rls_scopes"
    REQUIRE_MFA = "require_mfa"
    VIEW_ADMIN_AUDIT = "view_admin_audit"


ADMIN_CAPABILITY_LABELS: dict[str, str] = {
    "create_user": "Создание пользователя",
    "block_user": "Блокировка пользователя",
    "archive_user": "Архивирование пользователя",
    "assign_roles": "Назначение ролей",
    "assign_rls_scopes": "Назначение областей доступа / RLS",
    "require_mfa": "Требовать MFA",
    "view_admin_audit": "Просмотр аудита администрирования",
}


# ═══════════════════════════════════════════════════════════════════════
# Admin Principles
# ═══════════════════════════════════════════════════════════════════════

ADMIN_PRINCIPLES: tuple[str, ...] = (
    "Пользователь создаётся в Admin.",
    "Роли назначаются администратором портала.",
    "Для критичных ролей требуется MFA.",
    "Все изменения доступа аудируются.",
    "Удаление пользователя должно быть логическим (archive, не физическое удаление).",
    "RLS применяется на backend/DB/API уровне.",
    "Excel export и BI reports учитывают RLS пользователя.",
    "Plaintext passwords запрещены — только безопасный hash (bcrypt/argon2).",
    "Пароли никогда не отображаются в UI и не передаются в открытом виде.",
)


# ═══════════════════════════════════════════════════════════════════════
# Expanded Security Principles (RLS-specific)
# ═══════════════════════════════════════════════════════════════════════

RLS_RULES: tuple[str, ...] = (
    "RLS enforced on backend/API/DB level — never client-side.",
    "Excel export uses the same RLS as report UI.",
    "BI drill-down cannot reveal out-of-scope data.",
    "RLS applied BEFORE pagination — out-of-scope rows never counted.",
    "RLS applied BEFORE aggregation — out-of-scope data not in totals.",
    "RLS applied BEFORE drill-down — cannot navigate outside scope.",
    "RLS applied BEFORE Excel export — exported data respects scope.",
    "RLS applied BEFORE approval queue — only in-scope objects visible.",
    "Inside one scope type, scopes are OR (union).",
    "Across different scope types, scopes are AND (intersection).",
    "UI hiding is not security — manual URL/API call cannot bypass RLS.",
    "User cannot final-approve own object (maker-checker rule).",
    "Manifest publication requires final approval.",
    "Emergency stop requires MFA, reason, and audit entry.",
    "Device service account has no human portal UI access (machine-only).",
    "Advertiser sees only own campaigns and reports (advertiser_scope).",
    "Operations sees technical KSO state but not commercial terms.",
    "Admin user management does not bypass business approvals.",
    "Role/RLS changes are audited with timestamp and admin identity.",
)


# ═══════════════════════════════════════════════════════════════════════
# Role Portal Views — detailed role descriptions
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RolePortalView:
    """Full portal perspective for a given role."""
    role_id: str
    role_label: str
    primary_zone: str                          # главная зона ответственности
    allowed_pages: FrozenSet[str]              # доступные страницы
    primary_page: str                          # основной экран после входа
    allowed_actions: FrozenSet[str]            # разрешённые действия
    forbidden_actions: FrozenSet[str]           # явно запрещённые действия
    required_rls: FrozenSet[str]               # обязательные RLS scopes
    sees_commercial_data: bool                 # видит коммерческие данные
    sees_technical_data: bool                  # видит технические данные
    bi_excel_access: str                       # доступ к BI/Excel
    requires_mfa: bool                         # требуется MFA
    requires_audit: bool                        # все действия аудируются
    description: str                           # краткое описание


ROLE_PORTAL_VIEWS: tuple[RolePortalView, ...] = (
    RolePortalView(
        role_id="system_admin",
        role_label="Системный администратор",
        primary_zone="Полный доступ к платформе без RLS-ограничений",
        allowed_pages=frozenset({
            "/dashboard", "/stores", "/devices", "/creatives",
            "/campaigns", "/schedule", "/publications",
            "/proof-of-play", "/approvals", "/reports",
            "/deployment", "/admin",
        }),
        primary_page="/dashboard",
        allowed_actions=frozenset({
            "view_all", "manage_users", "manage_roles",
            "manage_devices", "export_reports", "view_audit",
            "publish_manifest", "approve_objects",
        }),
        forbidden_actions=frozenset(),
        required_rls=frozenset(),
        sees_commercial_data=True,
        sees_technical_data=True,
        bi_excel_access="Полный доступ ко всем BI-отчётам и Excel export без RLS-ограничений",
        requires_mfa=True,
        requires_audit=True,
        description="Полный административный доступ. Видит всю сеть, все кампании, всех рекламодателей.",
    ),
    RolePortalView(
        role_id="security_admin",
        role_label="Администратор безопасности",
        primary_zone="Управление пользователями, ролями, аудит безопасности",
        allowed_pages=frozenset({"/dashboard", "/admin"}),
        primary_page="/admin",
        allowed_actions=frozenset({
            "manage_users", "manage_roles", "view_audit",
            "assign_roles", "assign_rls_scopes", "require_mfa",
        }),
        forbidden_actions=frozenset({
            "view_campaigns", "view_creatives", "view_reports",
            "export_reports", "publish_manifest", "approve_objects",
        }),
        required_rls=frozenset(),
        sees_commercial_data=False,
        sees_technical_data=False,
        bi_excel_access="Нет доступа к BI-отчётам и Excel export",
        requires_mfa=True,
        requires_audit=True,
        description="Управление доступом и аудит. Не видит коммерческие данные, кампании и отчёты.",
    ),
    RolePortalView(
        role_id="ad_manager",
        role_label="Менеджер рекламы",
        primary_zone="Управление рекламными кампаниями, креативами, расписанием, публикацией",
        allowed_pages=frozenset({
            "/dashboard", "/stores", "/devices", "/creatives",
            "/campaigns", "/schedule", "/publications",
            "/proof-of-play", "/approvals", "/reports",
            "/deployment",
        }),
        primary_page="/campaigns",
        allowed_actions=frozenset({
            "view_campaigns", "view_creatives", "view_schedule",
            "view_publications", "view_proof_of_play",
            "approve_objects", "publish_manifest", "export_reports",
        }),
        forbidden_actions=frozenset({
            "manage_users", "manage_roles", "view_admin",
        }),
        required_rls=frozenset({
            "branch_scope", "store_scope", "campaign_scope",
            "device_scope", "approval_scope", "report_scope",
        }),
        sees_commercial_data=True,
        sees_technical_data=True,
        bi_excel_access="BI-отчёты и Excel export в рамках RLS (свои филиалы/кампании)",
        requires_mfa=False,
        requires_audit=True,
        description="Создание и управление кампаниями. Видит техническое состояние КСО для публикации.",
    ),
    RolePortalView(
        role_id="approver",
        role_label="Согласующий",
        primary_zone="Проверка и согласование креативов, кампаний, расписания, публикаций",
        allowed_pages=frozenset({
            "/dashboard", "/creatives", "/campaigns",
            "/schedule", "/publications", "/approvals", "/reports",
        }),
        primary_page="/approvals",
        allowed_actions=frozenset({
            "approve_objects", "view_approvals",
            "view_campaigns", "view_creatives", "view_reports",
        }),
        forbidden_actions=frozenset({
            "publish_manifest", "manage_users", "manage_roles",
            "view_admin", "view_devices", "view_stores",
            "manage_devices", "export_reports",
        }),
        required_rls=frozenset({
            "campaign_scope", "approval_scope", "report_scope",
        }),
        sees_commercial_data=True,
        sees_technical_data=False,
        bi_excel_access="Только просмотр BI-отчётов в своём approval scope. Excel export запрещён",
        requires_mfa=False,
        requires_audit=True,
        description="Проверка объектов согласования. Не видит технические данные КСО и магазинов.",
    ),
    RolePortalView(
        role_id="analyst",
        role_label="Аналитик",
        primary_zone="BI-отчётность, план/факт анализ, Excel export",
        allowed_pages=frozenset({
            "/dashboard", "/stores", "/devices", "/creatives",
            "/campaigns", "/schedule", "/publications",
            "/proof-of-play", "/reports",
        }),
        primary_page="/reports",
        allowed_actions=frozenset({
            "view_reports", "export_reports",
            "view_campaigns", "view_creatives", "view_proof_of_play",
        }),
        forbidden_actions=frozenset({
            "approve_objects", "publish_manifest",
            "manage_users", "manage_roles", "manage_devices",
            "view_admin", "view_deployment",
        }),
        required_rls=frozenset({
            "branch_scope", "store_scope", "campaign_scope",
            "device_scope", "report_scope",
        }),
        sees_commercial_data=True,
        sees_technical_data=True,
        bi_excel_access="BI-отчёты и Excel export в рамках RLS (свои филиалы/кампании/КСО)",
        requires_mfa=False,
        requires_audit=True,
        description="Аналитика и отчётность. Видит агрегированные данные, не управляет кампаниями.",
    ),
    RolePortalView(
        role_id="advertiser",
        role_label="Рекламодатель",
        primary_zone="Просмотр своих кампаний, креативов и отчётов",
        allowed_pages=frozenset({
            "/dashboard", "/creatives", "/campaigns",
            "/schedule", "/publications", "/proof-of-play",
            "/reports",
        }),
        primary_page="/campaigns",
        allowed_actions=frozenset({
            "view_campaigns", "view_creatives", "view_reports",
        }),
        forbidden_actions=frozenset({
            "approve_objects", "publish_manifest", "export_reports",
            "manage_users", "manage_roles", "manage_devices",
            "view_admin", "view_devices", "view_stores",
            "view_deployment", "view_approvals",
        }),
        required_rls=frozenset({
            "advertiser_scope", "campaign_scope", "report_scope",
        }),
        sees_commercial_data=True,
        sees_technical_data=False,
        bi_excel_access="Только просмотр BI-отчётов по своим кампаниям. Excel export запрещён",
        requires_mfa=False,
        requires_audit=True,
        description="Видит только свои кампании и креативы. Не видит сеть, устройства, согласования.",
    ),
    RolePortalView(
        role_id="operations",
        role_label="Оператор",
        primary_zone="Мониторинг магазинов, КСО, развёртывание",
        allowed_pages=frozenset({
            "/dashboard", "/stores", "/devices", "/deployment",
        }),
        primary_page="/devices",
        allowed_actions=frozenset({
            "view_stores", "view_devices", "manage_devices",
            "view_deployment",
        }),
        forbidden_actions=frozenset({
            "view_campaigns", "view_creatives", "view_schedule",
            "view_publications", "view_proof_of_play",
            "view_approvals", "view_reports",
            "approve_objects", "publish_manifest",
            "manage_users", "manage_roles", "export_reports",
            "view_admin",
        }),
        required_rls=frozenset({
            "branch_scope", "store_scope", "device_scope",
        }),
        sees_commercial_data=False,
        sees_technical_data=True,
        bi_excel_access="Нет доступа к BI-отчётам и Excel export",
        requires_mfa=False,
        requires_audit=True,
        description="Мониторинг технического состояния. Не видит коммерческие данные, кампании и отчёты.",
    ),
    RolePortalView(
        role_id="device_service",
        role_label="Сервис КСО",
        primary_zone="Техническое обслуживание КСО-устройств",
        allowed_pages=frozenset({"/deployment"}),
        primary_page="/deployment",
        allowed_actions=frozenset({
            "manage_devices", "view_devices", "view_deployment",
        }),
        forbidden_actions=frozenset({
            "view_dashboard", "view_stores", "view_campaigns",
            "view_creatives", "view_schedule", "view_publications",
            "view_proof_of_play", "view_approvals", "view_reports",
            "view_admin", "approve_objects", "publish_manifest",
            "manage_users", "manage_roles", "export_reports",
        }),
        required_rls=frozenset({
            "store_scope", "device_scope",
        }),
        sees_commercial_data=False,
        sees_technical_data=True,
        bi_excel_access="Нет доступа к BI-отчётам и Excel export",
        requires_mfa=False,
        requires_audit=False,
        description="Машинная учётная запись. Нет human UI-доступа к порталу, кроме deployment-статуса.",
    ),
)


# ═══════════════════════════════════════════════════════════════════════
# Page-Role Matrix — which roles see which pages
# ═══════════════════════════════════════════════════════════════════════

PAGE_ROLE_MATRIX: dict[str, FrozenSet[str]] = {
    "/dashboard": frozenset({
        "system_admin", "security_admin", "ad_manager",
        "approver", "analyst", "advertiser", "operations",
    }),
    "/stores": frozenset({
        "system_admin", "ad_manager", "analyst", "operations",
    }),
    "/devices": frozenset({
        "system_admin", "ad_manager", "analyst", "operations",
    }),
    "/creatives": frozenset({
        "system_admin", "ad_manager", "approver",
        "analyst", "advertiser",
    }),
    "/campaigns": frozenset({
        "system_admin", "ad_manager", "approver",
        "analyst", "advertiser",
    }),
    "/schedule": frozenset({
        "system_admin", "ad_manager", "approver",
        "analyst", "advertiser",
    }),
    "/publications": frozenset({
        "system_admin", "ad_manager", "approver",
        "analyst", "advertiser",
    }),
    "/proof-of-play": frozenset({
        "system_admin", "ad_manager", "analyst", "advertiser",
    }),
    "/approvals": frozenset({
        "system_admin", "ad_manager", "approver",
    }),
    "/reports": frozenset({
        "system_admin", "ad_manager", "approver",
        "analyst", "advertiser",
    }),
    "/deployment": frozenset({
        "system_admin", "ad_manager", "operations", "device_service",
    }),
    "/admin": frozenset({
        "system_admin", "security_admin",
    }),
    "/login": frozenset(),
    "/logout": frozenset(),
}


# ═══════════════════════════════════════════════════════════════════════
# Field Visibility Rules — forbidden fields per role
# ═══════════════════════════════════════════════════════════════════════

FORBIDDEN_FIELDS_ALL: FrozenSet[str] = frozenset({
    "device_secret", "access_token", "token", "authorization",
    "backend_url", "api_key",
    "password", "password_hash",
    "manifest_hash", "sha256", "fingerprint",
    "storage_key", "minio", "file_path", "filename",
    "campaign_id", "creative_id", "rendition_id",
    "store_id", "device_id", "schedule_item_id",
    "manifest_item_id", "booking_id",
    "device_event_id", "batch_id",
    "receipt_number", "card_number", "customer_id",
    "phone", "email", "fiscal_data",
    "sku_id", "price",
})


# ═══════════════════════════════════════════════════════════════════════
# Data Hierarchy (for RLS reference)
# ═══════════════════════════════════════════════════════════════════════

NETWORK_HIERARCHY: tuple[str, ...] = (
    "Сеть",
    "  → Филиал",
    "    → Кластер",
    "      → Магазин",
    "        → КСО",
)

COMMERCIAL_HIERARCHY: tuple[str, ...] = (
    "Рекламодатель",
    "  → Бренд",
    "    → Кампания",
    "      → Размещение",
    "        → Manifest",
    "          → PoP-событие",
    "            → Отчёт",
)
