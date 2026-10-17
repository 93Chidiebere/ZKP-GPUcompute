"""
DEPRECATED (kept for backward compatibility with sovereign-zk==0.3.0 imports).

SovereignClient.encrypt_data() produced a Fernet key per call but never
bound a commitment to the PLAINTEXT input -- see
sovereign_zk/protocol/commitments.py for the fix (commit_input() hashes the
plaintext + nonce + job_id, not the ciphertext, which is what the old
SovereignClient effectively did by hashing the already-encrypted payload).

The corrected client flow (client_demo.py) lives at the repository root,
not inside this installable package, because it's a runnable example that
talks to a specific local node -- it isn't something `pip install
sovereign-zk` should import as a library call. If you're running from a
checkout of the full repo, use:
    python3 client_demo.py
Otherwise, build on the protocol primitives directly:
    from sovereign_zk.protocol.commitments import commit_input, new_nonce
    from sovereign_zk.protocol.challenge import should_challenge, get_beacon
"""
import warnings

warnings.warn(
    "sovereign_zk.client.SovereignClient is deprecated and does not "
    "implement the commit-then-challenge protocol. See client_demo.py in "
    "the repository root, or build on sovereign_zk.protocol directly.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from client_demo import run_job, load_registered_model_commitment  # noqa: F401
except ImportError:
    pass  # client_demo.py is a repo-root example script, not part of this installed package
