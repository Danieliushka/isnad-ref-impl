#!/usr/bin/env python3
"""
isnad.batch — Batch verification and analysis for attestation sets.

Production use case: verify hundreds of attestations in one call,
get a structured report with pass/fail counts and details.
"""

from dataclasses import dataclass, field
from typing import Optional
import time

from .core import Attestation, TrustChain


@dataclass
class VerificationResult:
    """Result of verifying a single attestation."""
    attestation_id: str
    subject: str
    witness: str
    task: str
    valid: bool
    error: Optional[str] = None
    verify_time_ms: float = 0.0


@dataclass
class BatchReport:
    """Summary report from batch verification."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[VerificationResult] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def failed_results(self) -> list[VerificationResult]:
        return [r for r in self.results if not r.valid]

    def summary(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "failures": [
                {"id": r.attestation_id, "error": r.error}
                for r in self.failed_results
            ],
        }


def verify_batch(
    attestations: list[Attestation],
    *,
    fail_fast: bool = False,
) -> BatchReport:
    """
    Verify a batch of attestations.

    Args:
        attestations: List of Attestation objects to verify.
        fail_fast: If True, stop on first failure.

    Returns:
        BatchReport with per-attestation results and summary.
    """
    report = BatchReport(total=len(attestations))
    start = time.monotonic()

    for att in attestations:
        t0 = time.monotonic()
        error = None
        try:
            valid = att.verify()
            if not valid:
                error = "signature verification failed"
        except Exception as e:
            valid = False
            error = str(e)

        elapsed = (time.monotonic() - t0) * 1000
        result = VerificationResult(
            attestation_id=att.attestation_id,
            subject=att.subject,
            witness=att.witness,
            task=att.task,
            valid=valid,
            error=error,
            verify_time_ms=round(elapsed, 3),
        )
        report.results.append(result)

        if valid:
            report.passed += 1
        else:
            report.failed += 1
            if fail_fast:
                break

    report.elapsed_ms = (time.monotonic() - start) * 1000
    return report


def verify_chain_batch(
    chains: list[TrustChain],
) -> BatchReport:
    """
    Verify multiple trust chains at once.

    Each chain is verified by checking all its attestations.
    Returns a BatchReport where each result represents one chain.
    """
    report = BatchReport(total=len(chains))
    start = time.monotonic()

    for chain in chains:
        t0 = time.monotonic()
        error = None
        # A TrustChain only adds verified attestations via .add(),
        # so we re-verify each attestation individually.
        valid = True
        for att in chain.attestations:
            if not att.verify():
                valid = False
                error = f"attestation {att.attestation_id} failed verification"
                break

        elapsed = (time.monotonic() - t0) * 1000
        subject = chain.attestations[0].subject if chain.attestations else "empty"
        result = VerificationResult(
            attestation_id=f"chain:{subject}",
            subject=subject,
            witness="(chain)",
            task=f"{len(chain.attestations)} attestations",
            valid=valid,
            error=error,
            verify_time_ms=round(elapsed, 3),
        )
        report.results.append(result)

        if valid:
            report.passed += 1
        else:
            report.failed += 1

    report.elapsed_ms = (time.monotonic() - start) * 1000
    return report
