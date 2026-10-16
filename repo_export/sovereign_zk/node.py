"""
DEPRECATED (kept for backward compatibility with sovereign-zk==0.3.0 imports).

The original compute_proof() handler wrote decrypted plaintext to a
persistent-disk path ("temp_enclave_input.json") that was only cleaned up
on the success path (a mid-pipeline exception left it behind), and proved
every job unconditionally -- no sampling, which is the overhead the
concept note's probabilistic-audit design exists to avoid.

See sovereign_zk/enclave/simulated.py (tmpfs + guaranteed cleanup) and
prover_node.py (commit-then-challenge) in the repository root for the
fixed implementation. prover_node.py is a runnable example script, not
part of this installed package, for the same reason client_demo.py isn't
(see sovereign_zk/client.py's docstring).
"""
import warnings

warnings.warn(
    "sovereign_zk.node is deprecated: it leaked plaintext to disk on "
    "exception and proved every job (no sampling). Use prover_node.py in "
    "the repository root, or sovereign_zk.enclave.SimulatedEnclaveBackend "
    "directly.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from prover_node import app, run_node  # noqa: F401
except ImportError:
    pass  # prover_node.py is a repo-root example script, not part of this installed package
