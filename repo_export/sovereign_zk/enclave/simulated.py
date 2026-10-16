"""
SimulatedEnclaveBackend.

What this fixes from the original prototype (kenya_enclave_server.py /
sovereign_zk/node.py):
  1. Plaintext is now written to a tmpfs-backed directory (/dev/shm) when
     available, never to a persistent disk path -- /dev/shm is RAM-backed
     on Linux, so nothing here is written to a physical disk.
  2. The directory is created with mode 0700 (owner-only).
  3. Cleanup (secure overwrite-then-unlink) happens in a `finally` block,
     so a mid-pipeline exception in ezkl no longer leaves plaintext behind
     -- the original code's os.remove() call was never reached on failure.
  4. The attestation this backend returns says isolated_from_host=False,
     explicitly and truthfully, instead of printing "Admin cannot see
     this" / "AWS Nitro Enclave" while providing neither.

What this does NOT fix, because it cannot be fixed without real hardware:
there is still no isolation from a host administrator with process or
memory access while this code is running. Use NitroEnclaveBackend (or an
equivalent real TEE) for any deployment handling real sensitive data.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import warnings
from contextlib import contextmanager

from .base import EnclaveBackend, AttestationClaim, InferenceResult

os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))
import ezkl  # noqa: E402


def _secure_tmp_root() -> str:
    """Prefer tmpfs (RAM-backed) so plaintext never touches a physical
    disk. Falls back to a normal temp dir with a loud warning -- this
    matters if /dev/shm isn't available (e.g. some containers, Windows)."""
    if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
        return "/dev/shm"
    warnings.warn(
        "SimulatedEnclaveBackend: /dev/shm not writable; falling back to a "
        "disk-backed temp directory. Plaintext WILL touch physical storage "
        "briefly. This is acceptable for dev/testing only.",
        stacklevel=2,
    )
    return tempfile.gettempdir()


def _shred(path: str) -> None:
    """Best-effort overwrite before unlink. Not a guarantee against
    wear-leveling SSDs or copy-on-write filesystems -- the real fix is
    'never hits persistent disk' (tmpfs), which is why we prefer /dev/shm
    above. This is defense in depth for the fallback path."""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())
    except FileNotFoundError:
        return
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@contextmanager
def _ephemeral_dir():
    root = _secure_tmp_root()
    d = tempfile.mkdtemp(prefix="szk_enclave_", dir=root)
    os.chmod(d, 0o700)
    try:
        yield d
    finally:
        for name in os.listdir(d):
            _shred(os.path.join(d, name))
        shutil.rmtree(d, ignore_errors=True)


class SimulatedEnclaveBackend(EnclaveBackend):
    def attest(self) -> AttestationClaim:
        return AttestationClaim(
            backend_kind="simulated",
            isolated_from_host=False,
            attestation_document=None,
            detail=(
                "No hardware TEE. Plaintext is processed in an ordinary "
                "process; a host administrator with process/memory access "
                "can observe it while this runs. Use for protocol "
                "development and testing only."
            ),
        )

    def run_confidential_inference(self, plaintext_input: dict, onnx_compiled_path: str) -> InferenceResult:
        with _ephemeral_dir() as d:
            input_path = os.path.join(d, "input.json")
            witness_path = os.path.join(d, "witness.json")

            with open(input_path, "w") as f:
                json.dump(plaintext_input, f)
            os.chmod(input_path, 0o600)

            ezkl.gen_witness(input_path, onnx_compiled_path, witness_path)

            with open(witness_path, "r") as f:
                witness = json.load(f)
            output = witness.get("outputs", witness.get("output_data"))

            # Stash the witness path's contents in-memory for the caller in
            # case this job is challenged (avoids re-running inference);
            # the on-disk copy is still shredded on context exit.
            witness_bytes = json.dumps(witness).encode("utf-8")

        return InferenceResult(
            output={"output": output, "_witness_cache": witness_bytes},
            attestation=self.attest(),
        )
