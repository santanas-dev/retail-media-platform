"""KSO safety checks — enforce local interface contract rules.

This is a DEV TOOL. No secrets, no tokens, no network.
"""

from typing import Optional

# Allowed KSO states (from kso_local_interface_contract.md)
ALLOWED_STATES: frozenset[str] = frozenset({
    "idle",
    "transaction",
    "payment",
    "error",
    "service_mode",
    "unknown",
})


def can_show_ads(state: str, can_show_ads_flag: Optional[bool] = None) -> bool:
    """Check whether ads can be shown in the given KSO state.

    Rule (from kso_local_interface_contract.md):
        Ads can be shown ONLY if state == "idle" AND can_show_ads == True.

    If can_show_ads_flag is None, only the state is checked.
    """
    if state != "idle":
        return False
    if can_show_ads_flag is not None and not can_show_ads_flag:
        return False
    return True
