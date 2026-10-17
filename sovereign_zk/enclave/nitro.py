"""
NitroEnclaveBackend -- the real hardware-isolated path.

This module cannot be exercised in this development container: there is no
Nitro Enclave hardware here, no /dev/nsm device, and no network path to AWS
(the sandbox's egress allowlist does not include AWS endpoints). It is
written to the ACTUAL AWS Nitro Enclaves attestation pattern so it is
correct when deployed, not a mock. See DEPLOY_NITRO.md for the deployment
steps required to actually run it.

The pattern (this is how AWS's own `kmstool-enclave-cli` works, which this
module shells out to rather than reimplementing the NSM/attestation
protocol from scratch -- reimplementing attestation-document parsing and
COSE signature verification is exactly the kind of place a from-scratch
reimplementation would be easy to get subtly wrong):

  1. The enclave has NO direct network access. Its only path out is a
     vsock connection to a `vsock-proxy` process running on the PARENT
     EC2 instance, and that proxy is configured (vsock-proxy config file)
     to forward ONLY to the regional KMS endpoint -- nothing else. This is
     what makes "the host cannot read the data, and the enclave cannot
     exfiltrate it elsewhere" actually true, not just asserted.
  2. On startup, the enclave calls the NSM (Nitro Security Module) via
     /dev/nsm to request an attestation document. That document is signed
     by a key chaining to AWS's Nitro root CA and contains PCR0-PCR8
     measurements of exactly which enclave image (.eif) is running.
  3. To decrypt a ciphertext, the enclave calls KMS `Decrypt` with a
     `Recipient` parameter containing the attestation document plus an
     ephemeral RSA public key generated inside the enclave. KMS verifies
     the attestation chain AND checks the measured PCRs against the KMS
     key policy's enclave condition, THEN returns the plaintext re-wrapped
     under the ephemeral public key -- never in the clear over the wire.
     Only the enclave (holding the matching private key, which never
     leaves enclave memory) can unwrap it.
  4. The KMS key policy is therefore the actual root of the privacy
     guarantee: "this key only decrypts for callers who can produce a
     valid attestation document matching these PCR values." That policy
     must be set at deployment time (see DEPLOY_NITRO.md) -- it is not
     something this Python module can configure from inside the enclave.

Fail-closed by design: attest() and run_confidential_inference() raise
RuntimeError if /dev/nsm is absent, rather than silently falling back to
the simulated path. A privacy-critical backend that quietly degrades is
worse than one that refuses to run.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess

from .base import EnclaveBackend, AttestationClaim, InferenceResult
from .simulated import _ephemeral_dir  # reuse the tmpfs + shred machinery

NSM_DEVICE = "/dev/nsm"


class NotRunningInEnclaveError(RuntimeError):
    pass


def _require_enclave_environment() -> None:
    if not os.path.exists(NSM_DEVICE):
        raise NotRunningInEnclaveError(
            f"{NSM_DEVICE} not found. This process is not running inside an "
            "AWS Nitro Enclave. NitroEnclaveBackend refuses to run outside "
            "real enclave hardware -- see DEPLOY_NITRO.md. (If you are "
            "doing local development, use SimulatedEnclaveBackend instead, "
            "and keep that choice explicit in your deployment config.)"
        )
    if shutil.which("kmstool_enclave_cli") is None:
        raise NotRunningInEnclaveError(
            "kmstool_enclave_cli not found on PATH. This must be built into "
            "the enclave image (.eif) at build time -- see DEPLOY_NITRO.md. "
            "It is AWS's published tool (aws/aws-nitro-enclaves-sdk-c) for "
            "the attestation-bound KMS Decrypt call described in this "
            "module's docstring."
        )


class NitroEnclaveBackend(EnclaveBackend):
    def __init__(self, kms_key_id: str, region: str, vsock_proxy_port: int = 8000):
        self.kms_key_id = kms_key_id
        self.region = region
        self.vsock_proxy_port = vsock_proxy_port

    def attest(self) -> AttestationClaim:
        _require_enclave_environment()
        # A real deployment would call the NSM driver directly (via the
        # aws-nitro-enclaves-nsm-api crate's Python/FFI bindings) to pull
        # the raw attestation document for logging/audit purposes. That
        # binding is not installable in this container (no enclave kernel
        # module present to bind against), so this method's job here is
        # limited to the environment check above -- the attestation
        # document itself is produced and verified implicitly by KMS
        # during the Decrypt call in run_confidential_inference().
        return AttestationClaim(
            backend_kind="aws-nitro-enclave",
            isolated_from_host=True,
            attestation_document=None,  # see note above
            detail=(
                "Running with /dev/nsm present; KMS Decrypt calls in this "
                "process are bound to an attestation document verified by "
                "AWS KMS against the enclave image's PCR measurements."
            ),
        )

    def _kms_decrypt(self, ciphertext_b64: str) -> bytes:
        """Shells out to AWS's own kmstool_enclave_cli, which performs the
        attestation-bound Decrypt call described in the module docstring.
        Credentials (access key / secret / session token) must be supplied
        to the enclave via vsock from the parent instance at launch time --
        see DEPLOY_NITRO.md. This function does not handle credential
        provisioning itself."""
        proc = subprocess.run(
            [
                "kmstool_enclave_cli", "decrypt",
                "--region", self.region,
                "--proxy-port", str(self.vsock_proxy_port),
                "--key-id", self.kms_key_id,
                "--ciphertext", ciphertext_b64,
            ],
            check=True, capture_output=True, text=True, timeout=30,
        )
        # kmstool_enclave_cli prints base64 plaintext on success.
        return base64.b64decode(proc.stdout.strip())

    def run_confidential_inference(self, ciphertext_b64: str, onnx_compiled_path: str) -> InferenceResult:
        _require_enclave_environment()
        os.environ.setdefault("HOME", "/tmp")
        import ezkl  # imported here: only needed on this path, and only
                      # meaningful once we've confirmed we're in an enclave

        plaintext_bytes = self._kms_decrypt(ciphertext_b64)
        plaintext_input = json.loads(plaintext_bytes.decode("utf-8"))

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
            witness_bytes = json.dumps(witness).encode("utf-8")

        return InferenceResult(
            output={"output": output, "_witness_cache": witness_bytes},
            attestation=self.attest(),
        )
