"""
isnad Trust Report — Generate comprehensive markdown trust reports for chains.

Produces human-readable reports showing chain metadata, per-attestation
trust score breakdowns, overall chain score, and warnings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from isnad.core import Attestation, TrustChain


# ─── Warning Detection ─────────────────────────────────────────────

LOW_TRUST_THRESHOLD = 0.3
TAMPER_WARNING = "tamper_detected"
EXPIRED_WARNING = "expired"
LOW_TRUST_WARNING = "low_trust"


def _detect_warnings(
    attestation: Attestation,
    chain: TrustChain,
    now: Optional[datetime] = None,
    expiry_seconds: float = 86400 * 365,
) -> list[dict]:
    """Detect warnings for a single attestation."""
    warnings = []
    now = now or datetime.now(timezone.utc)

    # Tamper check
    if not attestation.verify():
        warnings.append({
            "type": TAMPER_WARNING,
            "message": f"Attestation {attestation.attestation_id} failed signature verification",
        })

    # Expiry check
    try:
        ts = datetime.fromisoformat(attestation.timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        if age > expiry_seconds:
            warnings.append({
                "type": EXPIRED_WARNING,
                "message": f"Attestation {attestation.attestation_id} expired ({age / 86400:.0f} days old)",
            })
    except (ValueError, TypeError):
        pass

    # Low trust for subject
    score = chain.trust_score(attestation.subject)
    if 0 < score < LOW_TRUST_THRESHOLD:
        warnings.append({
            "type": LOW_TRUST_WARNING,
            "message": f"Subject {attestation.subject} has low trust score ({score:.2f})",
        })

    return warnings


# ─── Report Generation ─────────────────────────────────────────────

def generate_trust_report(
    chain: TrustChain,
    chain_name: str = "Unnamed Chain",
    description: str = "",
    now: Optional[datetime] = None,
    expiry_seconds: float = 86400 * 365,
) -> str:
    """Generate a comprehensive markdown trust report for a chain.

    Args:
        chain: The TrustChain to report on.
        chain_name: Human-readable name for the chain.
        description: Optional description.
        now: Reference time for expiry checks (defaults to UTC now).
        expiry_seconds: Seconds after which an attestation is considered expired.

    Returns:
        Markdown-formatted trust report string.
    """
    now = now or datetime.now(timezone.utc)
    lines: list[str] = []

    # ── Header & Metadata ──
    lines.append(f"# Trust Report: {chain_name}")
    lines.append("")
    lines.append(f"**Generated:** {now.isoformat()}")
    lines.append(f"**Total Attestations:** {len(chain.attestations)}")
    unique_subjects = {a.subject for a in chain.attestations}
    unique_witnesses = {a.witness for a in chain.attestations}
    lines.append(f"**Unique Subjects:** {len(unique_subjects)}")
    lines.append(f"**Unique Witnesses:** {len(unique_witnesses)}")
    if description:
        lines.append(f"**Description:** {description}")
    lines.append("")

    # ── Per-Attestation Details ──
    lines.append("## Attestations")
    lines.append("")

    all_warnings: list[dict] = []

    if not chain.attestations:
        lines.append("_No attestations in chain._")
        lines.append("")
    else:
        for i, att in enumerate(chain.attestations, 1):
            valid = att.verify()
            status = "✅ Valid" if valid else "❌ Invalid"
            lines.append(f"### {i}. {att.task}")
            lines.append("")
            lines.append(f"| Field | Value |")
            lines.append(f"|-------|-------|")
            lines.append(f"| **ID** | `{att.attestation_id}` |")
            lines.append(f"| **Subject** | `{att.subject}` |")
            lines.append(f"| **Witness** | `{att.witness}` |")
            lines.append(f"| **Timestamp** | {att.timestamp} |")
            lines.append(f"| **Signature** | {status} |")
            if att.evidence:
                lines.append(f"| **Evidence** | {att.evidence} |")
            lines.append("")

            # Trust score for subject
            subj_score = chain.trust_score(att.subject)
            lines.append(f"**Subject Trust Score:** {subj_score:.2f}")
            lines.append("")

            # Warnings for this attestation
            att_warnings = _detect_warnings(att, chain, now=now, expiry_seconds=expiry_seconds)
            if att_warnings:
                lines.append("**⚠️ Warnings:**")
                for w in att_warnings:
                    lines.append(f"- [{w['type']}] {w['message']}")
                lines.append("")
            all_warnings.extend(att_warnings)

            lines.append("---")
            lines.append("")

    # ── Overall Chain Score ──
    lines.append("## Overall Chain Score")
    lines.append("")

    if unique_subjects:
        scores = {s: chain.trust_score(s) for s in unique_subjects}
        avg_score = sum(scores.values()) / len(scores)
        lines.append(f"**Average Trust Score:** {avg_score:.2f}")
        lines.append("")
        lines.append("| Agent | Trust Score |")
        lines.append("|-------|-------------|")
        for agent, score in sorted(scores.items(), key=lambda x: -x[1]):
            lines.append(f"| `{agent}` | {score:.2f} |")
        lines.append("")
    else:
        lines.append("_No subjects to score._")
        lines.append("")

    # ── Warnings Summary ──
    lines.append("## Warnings")
    lines.append("")

    if all_warnings:
        lines.append(f"**Total Warnings:** {len(all_warnings)}")
        lines.append("")
        # Group by type
        by_type: dict[str, list[dict]] = {}
        for w in all_warnings:
            by_type.setdefault(w["type"], []).append(w)
        for wtype, ws in by_type.items():
            lines.append(f"### {wtype} ({len(ws)})")
            lines.append("")
            for w in ws:
                lines.append(f"- {w['message']}")
            lines.append("")
    else:
        lines.append("✅ No warnings detected.")
        lines.append("")

    return "\n".join(lines)
