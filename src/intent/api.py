"""Intent-Commit API endpoints (L0-L3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .models import (
    IntentCommitment,
    IntentCommitRequest,
    IntentLevel,
    IntentRevealRequest,
    WitnessAck,
    verify_reveal,
)
from .validator import validate_commit, validate_reveal, IntentValidationError
from .cusum import CUSUMState, assess_l25, L25Assessment

router = APIRouter(prefix="/api/v1/intent", tags=["intent-commit"])

# In-memory stores (replace with PostgreSQL in production)
_commitments: dict[UUID, IntentCommitment] = {}
_cusum_states: dict[str, CUSUMState] = {}


class CommitResponse(BaseModel):
    id: UUID
    level: int
    status: str
    committed_at: datetime


class RevealResponse(BaseModel):
    id: UUID
    level: int
    status: str
    verified: bool
    revealed_at: datetime


class VerifyResponse(BaseModel):
    id: UUID
    level: int
    status: str
    hash_valid: Optional[bool] = None
    scope_declared: bool
    witnesses_count: int
    l25_assessment: Optional[dict] = None


class WitnessRequest(BaseModel):
    agent_id: str
    pubkey: str
    ack_signature: str


@router.post("/commit", response_model=CommitResponse)
async def create_commitment(req: IntentCommitRequest) -> CommitResponse:
    """Submit a new intent commitment (L0-L3)."""
    try:
        validate_commit(req)
    except IntentValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    commitment = IntentCommitment(
        agent_id=req.agent_id,
        level=req.level,
        commitment_hash=req.commitment_hash,
        scope=req.scope,
        signature=req.signature,
        intent_plaintext=req.intent_plaintext if req.level == IntentLevel.L0 else None,
    )
    _commitments[commitment.id] = commitment

    return CommitResponse(
        id=commitment.id,
        level=commitment.level,
        status=commitment.status,
        committed_at=commitment.committed_at,
    )


@router.post("/reveal", response_model=RevealResponse)
async def reveal_intent(req: IntentRevealRequest) -> RevealResponse:
    """Reveal the intent behind a commitment."""
    commitment = _commitments.get(req.commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")

    try:
        validate_reveal(commitment, req)
    except IntentValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    commitment.intent_plaintext = req.intent_plaintext
    commitment.nonce = req.nonce
    commitment.revealed_at = datetime.now(timezone.utc)
    commitment.status = "revealed"

    return RevealResponse(
        id=commitment.id,
        level=commitment.level,
        status=commitment.status,
        verified=True,
        revealed_at=commitment.revealed_at,
    )


@router.get("/{commitment_id}", response_model=dict)
async def get_commitment(commitment_id: UUID) -> dict:
    """Get commitment status and details."""
    commitment = _commitments.get(commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return commitment.model_dump(mode="json")


@router.get("/agent/{agent_id}")
async def list_agent_commitments(agent_id: str, limit: int = 50) -> list[dict]:
    """List an agent's commitments."""
    results = [
        c.model_dump(mode="json")
        for c in _commitments.values()
        if c.agent_id == agent_id
    ]
    return sorted(results, key=lambda x: x["committed_at"], reverse=True)[:limit]


@router.post("/{commitment_id}/witness")
async def add_witness(commitment_id: UUID, req: WitnessRequest) -> dict:
    """Add a witness acknowledgment to an L3 commitment."""
    commitment = _commitments.get(commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")

    if commitment.level < IntentLevel.L3:
        raise HTTPException(
            status_code=422,
            detail=f"Witnessing requires L3, commitment is L{commitment.level}",
        )

    ack = WitnessAck(
        agent_id=req.agent_id,
        pubkey=req.pubkey,
        ack_signature=req.ack_signature,
        ack_timestamp=datetime.now(timezone.utc),
    )
    commitment.witnesses.append(ack)

    return {
        "commitment_id": str(commitment_id),
        "witness_count": len(commitment.witnesses),
        "witness_added": req.agent_id,
    }


@router.get("/{commitment_id}/verify", response_model=VerifyResponse)
async def verify_commitment(commitment_id: UUID) -> VerifyResponse:
    """Verify a commitment's integrity."""
    commitment = _commitments.get(commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")

    hash_valid = None
    if commitment.commitment_hash and commitment.intent_plaintext and commitment.nonce:
        hash_valid = verify_reveal(
            commitment.commitment_hash,
            commitment.intent_plaintext,
            commitment.nonce,
            commitment.committed_at.isoformat(),
        )

    return VerifyResponse(
        id=commitment.id,
        level=commitment.level,
        status=commitment.status,
        hash_valid=hash_valid,
        scope_declared=commitment.scope is not None,
        witnesses_count=len(commitment.witnesses),
    )


@router.post("/{commitment_id}/assess-l25")
async def assess_commitment_l25(commitment_id: UUID, outcome: dict) -> dict:
    """Run L2.5 CUSUM anomaly assessment on a revealed commitment.

    Body: outcome dict with keys like tools_used, action_count, duration_seconds, value_usd.
    """
    commitment = _commitments.get(commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")

    if commitment.level < IntentLevel.L2:
        raise HTTPException(status_code=422, detail="L2.5 assessment requires L2+ commitment")

    if not commitment.scope:
        raise HTTPException(status_code=422, detail="Commitment has no scope to assess against")

    # Get or create CUSUM state for this agent
    if commitment.agent_id not in _cusum_states:
        _cusum_states[commitment.agent_id] = CUSUMState(agent_id=commitment.agent_id)

    state = _cusum_states[commitment.agent_id]
    commitment_dict = commitment.model_dump(mode="json")
    assessment = assess_l25(state, commitment_dict, outcome)

    return {
        "commitment_id": str(commitment_id),
        "agent_id": assessment.agent_id,
        "level": assessment.level,
        "deviation_score": assessment.deviation_score,
        "cusum_s_high": assessment.cusum_s_high,
        "n_observations": assessment.n_observations,
        "mean_deviation": assessment.mean_deviation,
        "passed": assessment.passed,
        "alarms": assessment.alarms,
    }
