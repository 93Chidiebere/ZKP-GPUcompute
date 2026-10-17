"""
Enclave backend interface.

Two implementations ship with this repo:
  - SimulatedEnclaveBackend: runs in a normal process. Provides NO
    isolation from a host administrator. Fixes the disk-plaintext leak from
    the original prototype but does not and cannot provide the privacy
    guarantee the concept note describes -- it exists for local development
    and protocol testing only, and labels itself as such at runtime.
  - NitroEnclaveBackend: the real AWS Nitro Enclaves attestation pattern.
    It FAILS CLOSED (raises, does not silently degrade) if it is not
    actually running inside a Nitro Enclave. It cannot be exercised in this
    development container -- there is no enclave hardware here -- see
    DEPLOY_NITRO.md for how to actually run it on EC2.

Both implement the same interface so the rest of the protocol (commitments,
challenge sampling, settlement) does not need to know which one is in use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AttestationClaim:
    """What the backend is asserting about its own execution environment."""
    backend_kind: str          # "simulated" | "aws-nitro-enclave"
    isolated_from_host: bool   # True only for a real, verified TEE
    attestation_document: bytes | None  # None for the simulated backend
    detail: str


@dataclass
class InferenceResult:
    output: object
    attestation: AttestationClaim


class EnclaveBackend(ABC):
    @abstractmethod
    def attest(self) -> AttestationClaim:
        """Return a claim about the execution environment. Callers (the
        gateway, the client) are responsible for deciding whether to trust
        a given backend_kind / isolated_from_host combination -- this
        method does not lie about what it is."""
        ...

    @abstractmethod
    def run_confidential_inference(self, plaintext_input: dict, onnx_model_path: str) -> InferenceResult:
        """Runs inference on plaintext_input. Implementations MUST ensure
        plaintext never persists on durable storage longer than strictly
        necessary for the inference call itself, and must guarantee cleanup
        even on exception (see simulated.py for the pattern)."""
        ...
