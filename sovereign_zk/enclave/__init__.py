from .base import EnclaveBackend, AttestationClaim, InferenceResult
from .simulated import SimulatedEnclaveBackend

__all__ = ["EnclaveBackend", "AttestationClaim", "InferenceResult", "SimulatedEnclaveBackend"]

# NitroEnclaveBackend is intentionally NOT imported here by default: importing
# it is cheap, but selecting it as your backend should be a deliberate,
# visible choice in calling code (prover_node.py), not something that
# happens implicitly via a package import.
