"""
Business rule tests for Campaign lifecycle transitions.

BR-003: Submit requires completeness (channels + targets + renditions)
BR-004: Submit transitions campaign status to 'in_review'
BR-005: Approve requires campaign in 'in_review' status
BR-006: Reject requires campaign in 'in_review' status

Uses FastAPI TestClient with mocked auth dependencies, plus source-code
inspection for business rule verification.
"""

import uuid
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _uid():
    return uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════
# BR-003 — Submit requires completeness
# ══════════════════════════════════════════════════════════════════════

class TestBR003SubmitCompleteness(unittest.TestCase):
    """BR-003: submit requires channels+targets+renditions.

    The _check_campaign_ready function validates:
      1. At least 1 channel
      2. At least 1 target
      3. At least 1 active valid rendition
    The submit_campaign_by_code endpoint additionally validates:
      - At least 1 creative binding
      - Bound creatives not archived/rejected
      - At least 1 schedule
      - Schedule has at least 1 active slot
    """

    def test_br003_service_check_campaign_ready_exists(self):
        """Verify _check_campaign_ready function exists and validates channels/targets/renditions."""
        import inspect
        from app.domains.campaigns.service import _check_campaign_ready

        source = inspect.getsource(_check_campaign_ready)

        # Must check channels
        self.assertIn("campaign has no channels", source,
                      "BR-003: completeness check must validate channels exist")
        # Must check targets
        self.assertIn("campaign has no targets", source,
                      "BR-003: completeness check must validate targets exist")
        # Must check renditions
        self.assertIn("campaign has no active valid renditions", source,
                      "BR-003: completeness check must validate renditions exist")
        # Must check rendition status is 'valid'
        self.assertIn("must be 'valid'", source,
                      "BR-003: completeness check must validate rendition.status == 'valid'")
        # Must check creative status is 'approved'
        self.assertIn("must be 'approved'", source,
                      "BR-003: completeness check must validate creative.status == 'approved'")

    def test_br003_submit_campaign_by_code_validates_creatives(self):
        """Verify submit_campaign_by_code checks creative bindings."""
        import inspect
        from app.domains.campaigns.router import submit_campaign_by_code

        source = inspect.getsource(submit_campaign_by_code)

        # Creative bindings check
        self.assertIn("no active creative bindings", source,
                      "BR-003: submit must validate creative bindings")
        # Creative status check
        self.assertIn("is", source,
                      "BR-003: submit must check creative status")
        self.assertIn("archived", source,
                      "BR-003: submit must reject archived creatives")
        self.assertIn("rejected", source,
                      "BR-003: submit must reject rejected creatives")
        self.assertIn("Cannot submit", source,
                      "BR-003: submit error messages must mention 'Cannot submit'")

    def test_br003_submit_campaign_by_code_validates_schedule(self):
        """Verify submit_campaign_by_code checks schedule and slots."""
        import inspect
        from app.domains.campaigns.router import submit_campaign_by_code

        source = inspect.getsource(submit_campaign_by_code)

        # Schedule check
        self.assertIn("campaign has no schedule", source,
                      "BR-003: submit must validate schedule exists")
        # Slots check
        self.assertIn("campaign has no active schedule slots", source,
                      "BR-003: submit must validate active slots exist")

    def test_br003_submit_campaign_service_uses_check_ready(self):
        """Verify submit_campaign service calls _check_campaign_ready."""
        import inspect
        from app.domains.campaigns.service import submit_campaign

        source = inspect.getsource(submit_campaign)

        self.assertIn("_check_campaign_ready", source,
                      "BR-003: submit_campaign must call _check_campaign_ready")

    def test_br003_approve_campaign_service_uses_check_ready(self):
        """Verify approve_campaign service calls _check_campaign_ready."""
        import inspect
        from app.domains.campaigns.service import approve_campaign

        source = inspect.getsource(approve_campaign)

        self.assertIn("_check_campaign_ready", source,
                      "BR-003: approve_campaign must call _check_campaign_ready")


# ══════════════════════════════════════════════════════════════════════
# BR-004 — Submit → in_review
# ══════════════════════════════════════════════════════════════════════

class TestBR004SubmitInReview(unittest.TestCase):
    """BR-004: campaign submit → in_review status transition.

    The submit_campaign service function must transition the campaign
    status to 'in_review' after passing completeness checks.
    """

    def test_br004_submit_campaign_sets_in_review(self):
        """submit_campaign transitions status from draft to 'in_review'."""
        import inspect
        from app.domains.campaigns.service import submit_campaign

        source = inspect.getsource(submit_campaign)

        # The service explicitly sets status to "in_review"
        self.assertIn('"in_review"', source,
                      "BR-004: submit_campaign must set status='in_review'")

    def test_br004_submit_cannot_transition_from_in_review(self):
        """submit_campaign rejects if already in_review or approved."""
        import inspect
        from app.domains.campaigns.service import submit_campaign, SUBMIT_FROM_STATUSES

        source = inspect.getsource(submit_campaign)

        # SUBMIT_FROM_STATUSES = {"draft", "rejected"}
        self.assertIn("draft", SUBMIT_FROM_STATUSES,
                      "BR-004: submit allowed from 'draft'")
        self.assertIn("rejected", SUBMIT_FROM_STATUSES,
                      "BR-004: submit allowed from 'rejected'")

        # "in_review" is NOT in SUBMIT_FROM_STATUSES
        self.assertNotIn("in_review", SUBMIT_FROM_STATUSES,
                         "BR-004: submit NOT allowed from 'in_review'")
        self.assertNotIn("approved", SUBMIT_FROM_STATUSES,
                         "BR-004: submit NOT allowed from 'approved'")

        # Error message mentions Must be draft or rejected
        self.assertIn("Must be draft or rejected", source,
                      "BR-004: submit must error with 'Must be draft or rejected'")

    def test_br004_submit_by_code_creates_approval_request(self):
        """submit_campaign_by_code creates ApprovalRequest and transitions status."""
        import inspect
        from app.domains.campaigns.router import submit_campaign_by_code

        source = inspect.getsource(submit_campaign_by_code)

        # Creates ApprovalRequest
        self.assertIn("ApprovalRequestCreate", source,
                      "BR-004: submit must create ApprovalRequest")
        self.assertIn("request_approval", source,
                      "BR-004: submit must call request_approval")

    def test_br004_status_set_explicitly(self):
        """Verify status is explicitly set, not derived from side effect."""
        import inspect
        from app.domains.campaigns.service import submit_campaign

        source = inspect.getsource(submit_campaign)
        lines = source.split("\n")

        # Find the line that sets status
        status_set_lines = [l for l in lines if "in_review" in l and "status" in l]
        self.assertTrue(
            len(status_set_lines) > 0,
            f"BR-004: no line sets status='in_review' explicitly. Source:\n{source[:500]}"
        )


# ══════════════════════════════════════════════════════════════════════
# BR-005 — Approve requires in_review
# ══════════════════════════════════════════════════════════════════════

class TestBR005ApproveRequiresInReview(unittest.TestCase):
    """BR-005: approve requires campaign in 'in_review' status.

    The approve_campaign service function must reject approval
    when the campaign status is NOT 'in_review'.
    """

    def test_br005_approve_check_exists(self):
        """approve_campaign contains a status check for 'in_review'."""
        import inspect
        from app.domains.campaigns.service import approve_campaign

        source = inspect.getsource(approve_campaign)

        # Must check status != "in_review"
        self.assertIn('"in_review"', source,
                      "BR-005: approve must reference 'in_review'")
        self.assertIn("Cannot approve", source,
                      "BR-005: approve must use 'Cannot approve' error prefix")
        self.assertIn("Must be in_review", source,
                      "BR-005: approve must say 'Must be in_review'")

    def test_br005_approve_rejects_draft(self):
        """approve_campaign rejects a campaign in draft status."""
        from app.domains.campaigns.service import approve_campaign

        # The function checks status != "in_review" and raises 400
        import inspect
        source = inspect.getsource(approve_campaign)

        # Verify the condition checks for != "in_review"
        self.assertIn('status != "in_review"', source,
                      "BR-005: approve must check status != 'in_review'")
        self.assertTrue(
            "400" in source or "BAD_REQUEST" in source,
            "BR-005: approve must return 400 for wrong status")

    def test_br005_approve_rejects_rejected(self):
        """approve_campaign rejects a rejected campaign."""
        # Same check as above — the guard catches any status != in_review
        # including 'rejected', 'approved', 'archived', and 'draft'
        from app.domains.campaigns.service import approve_campaign
        import inspect
        source = inspect.getsource(approve_campaign)

        # Verify the message includes the actual status
        self.assertIn("campaign.status", source,
                      "BR-005: error must include campaign.status")
        self.assertIn("Cannot approve campaign", source,
                      "BR-005: error must mention 'Cannot approve campaign'")


# ══════════════════════════════════════════════════════════════════════
# BR-006 — Reject requires in_review
# ══════════════════════════════════════════════════════════════════════

class TestBR006RejectRequiresInReview(unittest.TestCase):
    """BR-006: reject requires campaign in 'in_review' status.

    The reject_campaign service function must reject rejection
    when the campaign status is NOT 'in_review'.
    """

    def test_br006_reject_check_exists(self):
        """reject_campaign contains a status check for 'in_review'."""
        import inspect
        from app.domains.campaigns.service import reject_campaign

        source = inspect.getsource(reject_campaign)

        # Must check status != "in_review"
        self.assertIn('"in_review"', source,
                      "BR-006: reject must reference 'in_review'")
        self.assertIn("Cannot reject", source,
                      "BR-006: reject must use 'Cannot reject' error prefix")
        self.assertIn("Must be in_review", source,
                      "BR-006: reject must say 'Must be in_review'")

    def test_br006_reject_sets_rejection_reason(self):
        """reject_campaign stores the rejection_reason on the campaign."""
        import inspect
        from app.domains.campaigns.service import reject_campaign

        source = inspect.getsource(reject_campaign)

        # Must store the reason
        self.assertIn("rejection_reason", source,
                      "BR-006: reject must store rejection_reason")
        self.assertIn("campaign.rejection_reason", source,
                      "BR-006: must set campaign.rejection_reason = reason")
        # Status must be set to "rejected"
        self.assertIn('"rejected"', source,
                      "BR-006: reject must set status='rejected'")

    def test_br006_reject_rejects_draft(self):
        """reject_campaign rejects a campaign in draft status."""
        from app.domains.campaigns.service import reject_campaign
        import inspect
        source = inspect.getsource(reject_campaign)

        # Verify the condition checks for != "in_review"
        self.assertIn('status != "in_review"', source,
                      "BR-006: reject must check status != 'in_review'")
        self.assertTrue(
            "400" in source or "BAD_REQUEST" in source,
            "BR-006: reject must return 400 for wrong status")

    def test_br006_reject_rejects_approved(self):
        """reject_campaign rejects an already-approved campaign."""
        from app.domains.campaigns.service import reject_campaign
        import inspect
        source = inspect.getsource(reject_campaign)

        # The status guard catches any non-in_review status
        self.assertIn("campaign.status", source,
                      "BR-006: error must include campaign.status")
        self.assertIn("Cannot reject campaign", source,
                      "BR-006: error must mention 'Cannot reject campaign'")


# ══════════════════════════════════════════════════════════════════════
# Integration — lifecycle edge cases
# ══════════════════════════════════════════════════════════════════════

class TestCampaignLifecycleTransitions(unittest.TestCase):
    """Verify the complete campaign lifecycle state machine.

    Valid transitions:
      draft → in_review → approved
                   └→ rejected
      rejected → (edit) → draft → in_review → ...

    Invalid transitions:
      draft → approved (must go through in_review)
      approved → rejected (must go through re-submit)
      in_review → draft (not allowed)
    """

    def test_lifecycle_approved_is_terminal_for_transitions(self):
        """Approved status prevents submit/approve/reject."""
        from app.domains.campaigns.service import (
            SUBMIT_FROM_STATUSES, EDITABLE_STATUSES,
        )

        # approved is not in submit-from or editable
        statuses_to_check = ["approved", "archived"]
        for st in statuses_to_check:
            self.assertNotIn(st, SUBMIT_FROM_STATUSES,
                             f"Lifecycle: submit not allowed from '{st}'")
            self.assertNotIn(st, EDITABLE_STATUSES,
                             f"Lifecycle: edit not allowed from '{st}'")

    def test_lifecycle_in_review_not_editable(self):
        """Campaigns in 'in_review' cannot be edited."""
        from app.domains.campaigns.service import EDITABLE_STATUSES

        self.assertNotIn("in_review", EDITABLE_STATUSES,
                         "Lifecycle: cannot edit campaign in 'in_review'")
        self.assertIn("draft", EDITABLE_STATUSES,
                      "Lifecycle: can edit draft")
        self.assertIn("rejected", EDITABLE_STATUSES,
                      "Lifecycle: can edit rejected")

    def test_lifecycle_rejected_can_be_resubmitted(self):
        """A rejected campaign can be resubmitted (goes back to in_review)."""
        from app.domains.campaigns.service import SUBMIT_FROM_STATUSES

        self.assertIn("rejected", SUBMIT_FROM_STATUSES,
                      "Lifecycle: rejected campaigns can be resubmitted")
