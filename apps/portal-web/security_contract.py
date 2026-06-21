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
