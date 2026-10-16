import json
import os
import time
import warnings

import requests
from cryptography.fernet import Fernet

os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")
import ezkl


class SovereignClient:
    """Client for the current synthetic-data demonstration.

    The current node receives the Fernet key and can read the decrypted data.
    This client therefore refuses remote submissions unless the caller explicitly
    opts into the insecure demo flow. This opt-in is not suitable for PII.
    """

    def __init__(self, node_url: str, allow_insecure_demo: bool = False):
        self.node_url = node_url.rstrip("/")
        self.allow_insecure_demo = allow_insecure_demo
        self.fernet_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.fernet_key)

    def encrypt_data(self, data: dict, output_path: str):
        """Encrypt data for the demo transport; this does not hide it from the node."""
        plaintext = json.dumps(data).encode("utf-8")
        encrypted_data = self.cipher_suite.encrypt(plaintext)
        with open(output_path, "wb") as output:
            output.write(encrypted_data)
        return output_path

    def submit_compute_job(
        self,
        encrypted_data_path: str,
        model_path: str,
        pk_path: str,
        srs_path: str,
        output_proof_path: str,
    ):
        if not self.allow_insecure_demo:
            raise RuntimeError(
                "Remote submission is disabled: the demo node receives the "
                "Fernet key and can read plaintext. Set allow_insecure_demo=True "
                "only for synthetic data."
            )
        warnings.warn(
            "Insecure demo enabled: the remote node can decrypt and read the data. "
            "Never submit personal or confidential data.",
            RuntimeWarning,
            stacklevel=2,
        )

        headers = {"fernet-key": self.fernet_key.decode("utf-8")}
        with open(encrypted_data_path, "rb") as encrypted, \
             open(model_path, "rb") as model, \
             open(pk_path, "rb") as proving_key, \
             open(srs_path, "rb") as srs:
            files = {
                "encrypted_data": encrypted,
                "compiled_model": model,
                "pk_key": proving_key,
                "kzg_srs": srs,
            }
            response = requests.post(
                f"{self.node_url}/compute",
                files=files,
                headers=headers,
                timeout=300,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Node returned {response.status_code}: {response.text}"
            )

        with open(output_proof_path, "w", encoding="utf-8") as output:
            json.dump(response.json(), output)
        return True

    def verify_proof(
        self, proof_path: str, settings_path: str, vk_path: str, srs_path: str
    ):
        start_verify = time.time()
        is_valid = ezkl.verify(proof_path, settings_path, vk_path, srs_path)
        elapsed = time.time() - start_verify
        if is_valid:
            print(f"[SUCCESS] EZKL proof verified in {elapsed:.4f} seconds.")
        else:
            print("[ERROR] EZKL proof verification failed.")
        return bool(is_valid)


def test_client():
    print("=== SOVEREIGN-ZK SYNTHETIC-DATA DEMO ===")
    data_dict = {"input_data": [[0.8, 0.1, 0.9, 0.2, 0.5]]}
    client = SovereignClient(
        node_url="http://127.0.0.1:8000",
        allow_insecure_demo=True,
    )
    encrypted_path = "encrypted_transactions.bin"
    client.encrypt_data(data_dict, encrypted_path)
    proof_path = "proof.json"
    success = client.submit_compute_job(
        encrypted_path,
        "network.compiled",
        "pk.key",
        "kzg.srs",
        proof_path,
    )
    if success:
        client.verify_proof(proof_path, "settings.json", "vk.key", "kzg.srs")


if __name__ == "__main__":
    test_client()
