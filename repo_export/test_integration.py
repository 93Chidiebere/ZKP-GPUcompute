"""
In-process integration test. Uses Flask's test client (talks to the real
prover_node.app object directly -- same request handling code, no sockets)
so it runs reliably in CI / sandboxed environments without managing a
background server process.

Exercises:
  1. /attest reports isolated_from_host=False honestly for the simulated backend
  2. A forced-challenge job (audit_probability=1.0): node proves, client verifies
  3. A forced-skip job (audit_probability=0.0): no proof generated, output still returned
  4. Ledger hash-chain integrity, and that in-band commitments match the ledger
  5. A tampered ledger is detected (chain_valid flips to False)
"""
import io
import json
import os
import uuid

os.environ["SOVEREIGN_ZK_ALLOW_INSECURE_BEACON"] = "1"
os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))

from cryptography.fernet import Fernet

import prover_node
from sovereign_zk.protocol.commitments import commit_input, new_nonce
import ezkl

registered_c_w = json.load(open("model_commitment.json"))["c_w"]


def submit(client, audit_probability, input_data):
    prover_node.AUDIT_PROBABILITY = audit_probability
    job_id = str(uuid.uuid4())
    nonce = new_nonce()
    payload = {"input_data": input_data}
    c_x = commit_input(payload, nonce, job_id)

    key = Fernet.generate_key()
    ciphertext = Fernet(key).encrypt(json.dumps(payload).encode("utf-8"))

    resp = client.post(
        "/compute",
        data={"job_id": job_id, "c_x": c_x, "ciphertext": (io.BytesIO(ciphertext), "ciphertext.bin")},
        headers={"decrypt-key-hex": key.hex()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return job_id, c_x, resp.get_json()


def main():
    with prover_node.app.test_client() as client:
        print("=== 1. /attest ===")
        att = client.get("/attest").get_json()
        print(att)
        assert att["isolated_from_host"] is False, "simulated backend must honestly report no isolation"
        assert att["c_w"] == registered_c_w

        print("\n=== 2. forced CHALLENGE (audit_probability=1.0) ===")
        job_id, c_x, result = submit(client, 1.0, [[0.8, 0.1, 0.9, 0.2, 0.5]])
        print({k: v for k, v in result.items() if k != "proof"})
        assert result["challenged"] is True
        assert "proof" in result
        assert result["c_w"] == registered_c_w

        with open("settings.json") as f:
            pass  # sanity: file exists from model_setup.py
        with open("_proof_check.json", "w") as f:
            json.dump(result["proof"], f)
        valid = ezkl.verify("_proof_check.json", "settings.json", "vk.key", "kzg.srs")
        os.remove("_proof_check.json")
        print(f"ezkl.verify(...) -> {valid}")
        assert valid, "proof produced by the challenged path must verify"

        print("\n=== 3. forced SKIP (audit_probability=0.0) ===")
        job_id2, c_x2, result2 = submit(client, 0.0, [[0.1, 0.9, 0.2, 0.7, 0.05]])
        print({k: v for k, v in result2.items()})
        assert result2["challenged"] is False
        assert "proof" not in result2
        assert "output" in result2, "output must still be returned even when not challenged"

        print("\n=== 4. ledger integrity ===")
        ledger_resp = client.get("/ledger").get_json()
        print(f"chain_valid={ledger_resp['chain_valid']}  entries={len(ledger_resp['entries'])}")
        assert ledger_resp["chain_valid"] is True
        job_commits = [e for e in ledger_resp["entries"] if e["kind"] == "job_commit"]
        ids_seen = {e["payload"]["job_id"] for e in job_commits}
        assert job_id in ids_seen and job_id2 in ids_seen
        for e in job_commits:
            if e["payload"]["job_id"] == job_id:
                assert e["payload"]["c_x"] == c_x
                assert e["payload"]["c_y"] == result["c_y"]

        print("\n=== 5. tamper detection ===")
        from sovereign_zk.protocol.ledger import Ledger
        led = Ledger(prover_node.LEDGER.path)
        assert led.verify_chain() is True
        # simulate a malicious edit: flip one character in the stored file
        raw = open(prover_node.LEDGER.path).read()
        tampered = raw.replace(result["c_y"][:8], "deadbeef", 1)
        with open(prover_node.LEDGER.path, "w") as f:
            f.write(tampered)
        led2 = Ledger(prover_node.LEDGER.path)
        tamper_detected = not led2.verify_chain()
        print(f"tamper_detected={tamper_detected}")
        assert tamper_detected, "hash chain must break when an entry is edited"
        # restore for cleanliness
        with open(prover_node.LEDGER.path, "w") as f:
            f.write(raw)

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
