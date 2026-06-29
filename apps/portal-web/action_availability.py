"""Action Availability Service — unified action flags for portal UI.

Computes which actions are available per entity based on:
- Object status (draft, approved, archived, etc.)
- User permissions (from backend)
- Maker-checker constraint (can't approve own requests)

Used by: campaigns, creatives, publications, approvals, schedule pages.
"""

from __future__ import annotations


def campaign_actions(
    campaign_status: str,
    user_id: str | None = None,
    creator_id: str | None = None,
    has_approve_perm: bool = False,
    has_manage_perm: bool = False,
) -> dict[str, dict]:
    """Return action flags for a campaign row.

    Returns dict of {action_name: {available: bool, reason: str}}.
    """
    status = (campaign_status or "").lower()
    is_own = (user_id and creator_id and user_id == creator_id)

    actions = {}

    # Edit
    if status == "draft":
        if has_manage_perm:
            actions["edit"] = {"available": True, "reason": ""}
        else:
            actions["edit"] = {"available": False, "reason": "Недостаточно прав для редактирования"}
    elif status in ("in_review", "approved"):
        actions["edit"] = {"available": False, "reason": "Нельзя редактировать после отправки на согласование"}
    elif status == "archived":
        actions["edit"] = {"available": False, "reason": "Кампания в архиве"}
    else:
        actions["edit"] = {"available": False, "reason": "Действие недоступно для этого статуса"}

    # Submit for review
    if status == "draft":
        if has_manage_perm:
            actions["submit"] = {"available": True, "reason": ""}
        else:
            actions["submit"] = {"available": False, "reason": "Недостаточно прав"}
    elif status == "rejected":
        if has_manage_perm:
            actions["submit"] = {"available": True, "reason": "Можно повторно отправить после исправления"}
        else:
            actions["submit"] = {"available": False, "reason": "Недостаточно прав"}
    elif status == "in_review":
        actions["submit"] = {"available": False, "reason": "Кампания уже на согласовании"}
    elif status == "approved":
        actions["submit"] = {"available": False, "reason": "Кампания уже одобрена"}
    else:
        actions["submit"] = {"available": False, "reason": "Действие недоступно"}

    # Approve
    if status == "in_review":
        if has_approve_perm:
            if is_own:
                actions["approve"] = {"available": False, "reason": "Нельзя согласовать собственную кампанию"}
            else:
                actions["approve"] = {"available": True, "reason": ""}
        else:
            actions["approve"] = {"available": False, "reason": "Требуются права утверждающего"}
    else:
        actions["approve"] = {"available": False, "reason": "Кампания не на согласовании"}

    # Reject
    if status == "in_review":
        if has_approve_perm:
            if is_own:
                actions["reject"] = {"available": False, "reason": "Нельзя отклонить собственную кампанию"}
            else:
                actions["reject"] = {"available": True, "reason": ""}
        else:
            actions["reject"] = {"available": False, "reason": "Требуются права утверждающего"}
    else:
        actions["reject"] = {"available": False, "reason": "Кампания не на согласовании"}

    # Prepare publication
    if status == "approved":
        if has_manage_perm:
            actions["prepare_publication"] = {"available": True, "reason": ""}
        else:
            actions["prepare_publication"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["prepare_publication"] = {"available": False, "reason": "Кампания должна быть одобрена"}

    # Archive
    if status == "archived":
        actions["archive"] = {"available": False, "reason": "Кампания уже в архиве"}
    else:
        if has_manage_perm:
            actions["archive"] = {"available": True, "reason": ""}
        else:
            actions["archive"] = {"available": False, "reason": "Недостаточно прав"}

    # Add creative
    if status in ("draft", "rejected"):
        if has_manage_perm:
            actions["add_creative"] = {"available": True, "reason": ""}
        else:
            actions["add_creative"] = {"available": False, "reason": "Недостаточно прав"}
    elif status in ("in_review", "approved"):
        actions["add_creative"] = {"available": False, "reason": "Нельзя менять состав после отправки на согласование"}
    else:
        actions["add_creative"] = {"available": False, "reason": "Действие недоступно"}

    return actions


def creative_actions(
    creative_status: str,
    has_moderate_perm: bool = False,
    has_manage_perm: bool = False,
) -> dict[str, dict]:
    """Return action flags for a creative."""
    status = (creative_status or "").lower()

    actions = {}

    # Submit for review
    if status in ("draft", "validation_failed", "pending_review"):
        if has_manage_perm:
            actions["submit_review"] = {"available": True, "reason": ""}
        else:
            actions["submit_review"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["submit_review"] = {"available": False, "reason": "Креатив уже отправлен на проверку"}

    # Approve
    if status in ("in_review", "pending_review", "manual_review"):
        if has_moderate_perm:
            actions["approve"] = {"available": True, "reason": ""}
        else:
            actions["approve"] = {"available": False, "reason": "Требуются права модератора"}
    else:
        actions["approve"] = {"available": False, "reason": "Креатив не на проверке"}

    # Reject
    if status in ("in_review", "pending_review", "manual_review"):
        if has_moderate_perm:
            actions["reject"] = {"available": True, "reason": ""}
        else:
            actions["reject"] = {"available": False, "reason": "Требуются права модератора"}
    else:
        actions["reject"] = {"available": False, "reason": "Креатив не на проверке"}

    # Archive
    if status != "archived":
        if has_manage_perm:
            actions["archive"] = {"available": True, "reason": ""}
        else:
            actions["archive"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["archive"] = {"available": False, "reason": "Креатив уже в архиве"}

    return actions


def publication_batch_actions(
    batch_status: str,
    has_manage_perm: bool = False,
    has_approve_perm: bool = False,
) -> dict[str, dict]:
    """Return action flags for a publication batch."""
    status = (batch_status or "").lower()

    actions = {}

    if status == "draft":
        if has_manage_perm:
            actions["request_approval"] = {"available": True, "reason": ""}
        else:
            actions["request_approval"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["request_approval"] = {"available": False, "reason": "Пакет не в черновике"}

    if status == "approved":
        if has_manage_perm:
            actions["generate"] = {"available": True, "reason": ""}
        else:
            actions["generate"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["generate"] = {"available": False, "reason": "Пакет не одобрен"}

    if status == "manifest_generated":
        if has_manage_perm:
            actions["publish"] = {"available": True, "reason": "Только в системе, доставка на КСО заблокирована"}
        else:
            actions["publish"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["publish"] = {"available": False, "reason": "Пакет показа не сформирован"}

    if status not in ("published", "cancelled"):
        if has_manage_perm:
            actions["cancel"] = {"available": True, "reason": ""}
        else:
            actions["cancel"] = {"available": False, "reason": "Недостаточно прав"}
    else:
        actions["cancel"] = {"available": False, "reason": "Пакет уже завершён"}

    return actions
