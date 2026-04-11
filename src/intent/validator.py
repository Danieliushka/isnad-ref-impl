"""Validation logic for intent commitments at each level."""

from __future__ import annotations

from .models import (
    IntentCommitRequest,
    IntentCommitment,
    IntentLevel,
    IntentRevealRequest,
    verify_reveal,
)


class IntentValidationError(Exception):
    """Raised when an intent commitment or reveal fails validation."""
    pass


def validate_commit(req: IntentCommitRequest) -> None:
    """Validate a commitment request based on its level.

    Raises IntentValidationError on failure.
    """
    if req.level == IntentLevel.L0:
        if not req.intent_plaintext:
            raise IntentValidationError("L0 requires intent_plaintext")

    if req.level >= IntentLevel.L1:
        if not req.commitment_hash:
            raise IntentValidationError(f"L{req.level} requires commitment_hash")

    if req.level >= IntentLevel.L2:
        if not req.scope:
            raise IntentValidationError(f"L{req.level} requires scope declaration")
        if not req.signature:
            raise IntentValidationError(f"L{req.level} requires Ed25519 signature")

    # L3 witnesses are added after initial commit via /witness endpoint


def validate_reveal(
    commitment: IntentCommitment,
    reveal: IntentRevealRequest,
) -> None:
    """Validate a reveal against a stored commitment.

    Raises IntentValidationError on failure.
    """
    if commitment.status != "committed":
        raise IntentValidationError(
            f"Commitment status is '{commitment.status}', expected 'committed'"
        )

    if commitment.level == IntentLevel.L0:
        # L0 has no hash to verify — just record the reveal
        return

    if not commitment.commitment_hash:
        raise IntentValidationError("Commitment has no hash to verify against")

    if not verify_reveal(
        commitment.commitment_hash,
        reveal.intent_plaintext,
        reveal.nonce,
        reveal.timestamp,
    ):
        raise IntentValidationError("Reveal does not match commitment hash")
