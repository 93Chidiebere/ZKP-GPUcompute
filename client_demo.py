"""
Client (replaces nigeria_client.py).

Fixes from the original prototype:
  - C_X is now computed over the PLAINTEXT input + nonce + job_id (old code
    hashed encrypted_payload + nonce + job_id, which binds nothing to the
    actual data -- see protocol/commitments.py docstring).
  - The node's C_W is checked against the model commitment this client
    actually registered for (model_commitment.json from model_setup.py),
    not trusted blindly -- this is what stops a "cheaper model"
    substitution (round-1 review, M2/M3).
  - Before trusting ANY response, the client pulls /ledger and recomputes
    the hash chain itself, and checks that the job_commit entry for this
    job_id matches the c_x/c_w/c_y the node claimed in-band. A node can
    still lie about the raw output on an unaudited job (that's what the
    economic deterrence bound in protocol/deterrence.py is for -- it isn't
    free, it's priced), but it can no longer silently rewrite history, and
    it cannot choose which jobs get challenged after the fact.
"""

from __future__ import annotations

import json
import os
import uuid

import requests
from cryptography.fernet import Fernet

os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))
import ezkl

from sovereign_zk.protocol.commitments import commit_input, commit_output, new_nonce


def load_registered_model_commitment(path="model_commitment.json") -> str:
    with open(path) as f:
        return json.load(f)["c_w"]


def verify_ledger(node_url: str, job_id: str, expected_c_x: str, expected_c_w: str, expected_c_y: str) -> bool:
    resp = requests.get(f"{node_url}/ledger", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data["chain_valid"]:
        print("[!] LEDGER TAMPER DETECTED: hash chain does not verify.")
        return False
    for entry in data["entries"]:
        if entry["kind"] == "job_commit" and entry["payload"]["job_id"] == job_id:
            p = entry["payload"]
            ok = (p["c_x"] == expected_c_x and p["c_w"] == expected_c_w and p["c_y"] == expected_c_y)
            if not ok:
                print("[!] Ledger entry does not match in-band response -- node is lying.")
            return ok
    print(f"[!] No job_commit entry found in ledger for job_id={job_id}")
    return False


def run_job(node_url: str, plaintext_input: dict, registered_c_w: str):
    job_id = str(uuid.uuid4())
    nonce = new_nonce()
    c_x = commit_input(plaintext_input, nonce, job_id)

    key = Fernet.generate_key()
    ciphertext = Fernet(key).encrypt(json.dumps(plaintext_input).encode("utf-8"))

    print(f"[*] job_id={job_id}")
    print(f"[*] C_X (input commitment) = {c_x}")

    resp = requests.post(
        f"{node_url}/compute",
        data={"job_id": job_id, "c_x": c_x},
        files={"ciphertext": ciphertext},
        headers={"decrypt-key-hex": key.hex()},
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()

    if result["c_w"] != registered_c_w:
        print(f"[!] MODEL SUBSTITUTION DETECTED: node used C_W={result['c_w']}, expected {registered_c_w}")
        return None

    if not verify_ledger(node_url, job_id, c_x, result["c_w"], result["c_y"]):
        print("[!] Aborting: ledger did not corroborate the node's response.")
        return None

    if result["challenged"]:
        print("[*] Job was CHALLENGED -- a full ZK proof was generated. Verifying...")
        proof_path = "received_proof.json"
        with open(proof_path, "w") as f:
            json.dump(result["proof"], f)
        is_valid = ezkl.verify(proof_path, "settings.json", "vk.key", "kzg.srs")
        os.remove(proof_path)
        if not is_valid:
            print("[ERROR] Proof FAILED verification. Reject result, trigger slashing (see gateway_server.py).")
            return None
        print(f"[SUCCESS] Proof verified cryptographically ({result.get('prove_seconds', 0):.2f}s to generate).")
    else:
        print("[*] Job was NOT challenged this round -- output accepted on economic deterrence, "
              "not a proof. This is the whole point of sampling (Sec. 3.1 of the concept note): "
              "it is cheap ONLY because most jobs don't carry this cost, and that's only safe if "
              "the node's posted stake actually satisfies S > gain/audit_probability.")

    print(f"[+] output = {result['output']}")
    print(f"[+] backend isolated_from_host = {result['backend_isolated_from_host']}")
    return result


def main():
    node_url = os.environ.get("SOVEREIGN_ZK_NODE_URL", "http://127.0.0.1:8000")

    att = requests.get(f"{node_url}/attest", timeout=10).json()
    print(f"[*] Node backend: {att['backend_kind']}  isolated_from_host={att['isolated_from_host']}")
    if not att["isolated_from_host"]:
        print("[!] This node provides NO hardware isolation. Do not send real sensitive data to it.")

    registered_c_w = load_registered_model_commitment()
    if att["c_w"] != registered_c_w:
        print(f"[!] Node is serving an unrecognized model (C_W mismatch). Refusing to submit job.")
        return

    sample_input = {"input_data": [[0.8, 0.1, 0.9, 0.2, 0.5]]}
    run_job(node_url, sample_input, registered_c_w)


if __name__ == "__main__":
    main()
