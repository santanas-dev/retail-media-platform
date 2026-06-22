"""
Proof-of-Play domain — KSO technical validation models.

KsoProofOfPlayEvent is a BRIDGE table for test KSO chain validation.
NOT a final enterprise PoP model — enterprise PoP lives in
device_gateway.models.ProofOfPlayEvent.
"""

from app.domains.proof_of_play.models import KsoProofOfPlayEvent

__all__ = ["KsoProofOfPlayEvent"]
