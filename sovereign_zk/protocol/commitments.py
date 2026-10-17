"""
Commitment scheme for Sovereign-ZK.

Fixes a gap from the earlier prototype: the old C_x was computed over the
*ciphertext* (encrypted_payload + nonce + job_id), which does not bind the
proof to the plaintext input at all -- a node could decrypt, substitute a
different plaintext, and the commitment would still "match" whatever
ciphertext was sent.

This module commits to:
  - C_X : the plaintext input            (bound with a high-entropy nonce)
  - C_W : the model/circuit being served (compiled circuit + verification key)
  - C_Y : the output, post-inference

All three are required for the audit relation described in the concept note
(Sec. 2.3): the ZK proof is only meaningful if it is checked against a
SPECIFIC declared model and a SPECIFIC declared input, not just "some model,
some input".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass


NONCE_BYTES = 32  # 256-bit nonce -> not brute-forceable even for low-entropy inputs


def new_nonce() -> bytes:
    """High-entropy nonce. Must be kept secret by the client until the
    reveal phase (challenge), otherwise C_X can be brute-forced for small
    input spaces (e.g. a single categorical transaction type)."""
    return os.urandom(NONCE_BYTES)


def _canonical_bytes(obj) -> bytes:
    """Deterministic serialization so the same logical input always hashes
    the same way regardless of dict key order / float formatting quirks."""
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def commit_input(plaintext_input, nonce: bytes, job_id: str) -> str:
    """C_X = SHA256(plaintext_input || nonce || job_id)

    Binds the commitment to the ACTUAL input data (not the ciphertext), the
    nonce (anti-brute-force), and the job_id (anti-replay across jobs).
    """
    h = hashlib.sha256()
    h.update(_canonical_bytes(plaintext_input))
    h.update(nonce)
    h.update(job_id.encode("utf-8"))
    return h.hexdigest()


def commit_output(output, job_id: str, salt: bytes | None = None) -> tuple[str, bytes]:
    """C_Y = SHA256(output || job_id || salt)

    The provider computes and publishes this BEFORE challenge randomness is
    revealed (commit-then-challenge, Sec. 2.2). A fresh salt is generated so
    the provider cannot be forced to reveal low-entropy outputs by brute
    force before the challenge phase.
    Returns (commitment_hex, salt) -- the node must retain `salt` to reveal
    later if challenged.
    """
    if salt is None:
        salt = os.urandom(NONCE_BYTES)
    h = hashlib.sha256()
    h.update(_canonical_bytes(output))
    h.update(job_id.encode("utf-8"))
    h.update(salt)
    return h.hexdigest(), salt


def commit_model(compiled_model_path: str, vk_path: str) -> str:
    """C_W = SHA256(compiled_circuit_bytes || verification_key_bytes)

    Published once when a node registers a model version. The gateway/
    client checks the node's claimed C_W against a registry of approved
    model commitments before trusting any proof from that node -- this is
    what stops a "cheaper model substitution" attack (round-1 review, M2).
    """
    h = hashlib.sha256()
    with open(compiled_model_path, "rb") as f:
        h.update(f.read())
    with open(vk_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def verify_input_commitment(plaintext_input, nonce: bytes, job_id: str, claimed_c_x: str) -> bool:
    return hmac.compare_digest(commit_input(plaintext_input, nonce, job_id), claimed_c_x)


def verify_output_commitment(output, job_id: str, salt: bytes, claimed_c_y: str) -> bool:
    computed, _ = commit_output(output, job_id, salt=salt)
    return hmac.compare_digest(computed, claimed_c_y)


@dataclass
class JobCommitments:
    job_id: str
    c_x: str
    c_w: str
    c_y: str | None = None
    output_salt_hex: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "c_x": self.c_x,
            "c_w": self.c_w,
            "c_y": self.c_y,
            "output_salt_hex": self.output_salt_hex,
        }
