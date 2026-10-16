"""Reference state machine for dispute-triggered ZK audits.

This module coordinates commitments and challenge deadlines. It does not implement
TEE attestation, a ZK circuit, proof verification, persistence, or economic slashing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable, Dict, Optional


def commitment(domain: str, value: bytes, nonce: bytes) -> str:
    """Create a salted, domain-separated SHA-256 commitment.

    Use a fresh high-entropy nonce for each commitment. A commitment is binding
    under SHA-256 and hides low-entropy values only when the nonce is secret and
    unpredictable. This is not an encryption function.
    """
    if not domain or not isinstance(value, bytes) or not isinstance(nonce, bytes):
        raise ValueError("domain, value, and nonce are required")
    if len(nonce) < 32:
        raise ValueError("nonce must contain at least 32 bytes")
    payload = (
        b"sovereign-zk:v1:"
        + domain.encode("utf-8")
        + b":"
        + len(value).to_bytes(8, "big")
        + value
        + nonce
    )
    return sha256(payload).hexdigest()


class JobState(str, Enum):
    COMMITTED = "committed"
    CHALLENGED = "challenged"
    PROVED = "proved"
    ACCEPTED = "accepted"
    SLASHED = "slashed"


@dataclass
class JobRecord:
    job_id: str
    model_commitment: str
    input_commitment: str
    output_commitment: str
    challenge_deadline: int
    state: JobState = JobState.COMMITTED
    proof_digest: Optional[str] = None
    failure_reason: Optional[str] = None


ProofVerifier = Callable[[JobRecord, bytes], bool]


class ChallengeProtocol:
    """In-memory commit-then-dispute state machine.

    A production integration must make commitments and transitions durable,
    verify a proof bound to all three commitments, and connect SLASHED outcomes
    to an enforceable bond or contract.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}

    def commit_job(
        self,
        job_id: str,
        model_commitment: str,
        input_commitment: str,
        output_commitment: str,
        challenge_deadline: int,
        now: int,
    ) -> JobRecord:
        if not job_id or job_id in self._jobs:
            raise ValueError("job_id must be non-empty and unique")
        for value in (model_commitment, input_commitment, output_commitment):
            if len(value) != 64:
                raise ValueError("commitments must be 32-byte hex digests")
            try:
                bytes.fromhex(value)
            except ValueError as exc:
                raise ValueError("commitments must be 32-byte hex digests") from exc
        if challenge_deadline <= now:
            raise ValueError("challenge_deadline must be in the future")

        record = JobRecord(
            job_id=job_id,
            model_commitment=model_commitment.lower(),
            input_commitment=input_commitment.lower(),
            output_commitment=output_commitment.lower(),
            challenge_deadline=challenge_deadline,
        )
        self._jobs[job_id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError("unknown job_id") from exc

    def challenge(self, job_id: str, now: int) -> JobRecord:
        record = self.get_job(job_id)
        if record.state is not JobState.COMMITTED:
            raise ValueError("only an unchallenged committed job can be challenged")
        if now > record.challenge_deadline:
            raise ValueError("challenge window has expired")
        record.state = JobState.CHALLENGED
        return record

    def submit_proof(
        self,
        job_id: str,
        proof: bytes,
        verifier: ProofVerifier,
        now: int,
    ) -> JobRecord:
        record = self.get_job(job_id)
        if record.state is not JobState.CHALLENGED:
            raise ValueError("proof is accepted only for a challenged job")
        if now > record.challenge_deadline:
            record.state = JobState.SLASHED
            record.failure_reason = "proof submitted after challenge deadline"
            return record
        if not proof:
            record.state = JobState.SLASHED
            record.failure_reason = "empty proof"
            return record
        if verifier(record, proof):
            record.state = JobState.PROVED
            record.proof_digest = sha256(proof).hexdigest()
        else:
            record.state = JobState.SLASHED
            record.failure_reason = "proof verification failed"
        return record

    def finalize(self, job_id: str, now: int) -> JobRecord:
        record = self.get_job(job_id)
        if now < record.challenge_deadline:
            raise ValueError("cannot finalize before the challenge window closes")
        if record.state is JobState.COMMITTED:
            record.state = JobState.ACCEPTED
        elif record.state is JobState.CHALLENGED:
            record.state = JobState.SLASHED
            record.failure_reason = "provider did not prove the challenged result"
        elif record.state not in (JobState.PROVED, JobState.SLASHED, JobState.ACCEPTED):
            raise ValueError("job is in an invalid state")
        return record
