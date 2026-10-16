"""
Prover node (replaces kenya_enclave_server.py / sovereign_zk/node.py).

Correct ordering per challenge.py's docstring and the round-2 review (A5):

  1. decrypt + run inference INSIDE the enclave backend (TEE-isolated if
     NitroEnclaveBackend is configured; unisolated if SimulatedEnclaveBackend
     -- the backend's own attest() call is always honest about which)
  2. compute C_Y and APPEND IT TO THE LEDGER (this is the public commitment,
     made before challenge randomness is read)
  3. only THEN read the beacon and decide should_challenge()
  4. if challenged: run the expensive ezkl.prove() step and return a proof
     if not challenged: return the output + commitments only (no proof) --
     this is what keeps the 99% case near-native speed (concept note Sec. 3.1)

Every job commit, challenge decision, and proof result is appended to a
local hash-chained ledger (protocol/ledger.py) so the sequence of events is
independently checkable afterward, rather than only existing in a server
log an operator could edit.
"""

from __future__ import annotations

import json
import os
import time

from flask import Flask, request, jsonify

os.environ.setdefault("HOME", os.environ.get("USERPROFILE", "/tmp"))
import ezkl

from sovereign_zk.enclave.simulated import SimulatedEnclaveBackend
from sovereign_zk.protocol.commitments import commit_output, commit_model
from sovereign_zk.protocol.challenge import get_beacon, should_challenge
from sovereign_zk.protocol.ledger import Ledger

app = Flask(__name__)
BACKEND = SimulatedEnclaveBackend()  # swap for NitroEnclaveBackend(...) in a real deployment
LEDGER = Ledger(os.environ.get("SOVEREIGN_ZK_LEDGER_PATH", "node_ledger.jsonl"))
AUDIT_PROBABILITY = float(os.environ.get("SOVEREIGN_ZK_AUDIT_PROBABILITY", "0.01"))

MODEL_PATH = "network.compiled"
VK_PATH = "vk.key"
PK_PATH = "pk.key"
SRS_PATH = "kzg.srs"


@app.route("/attest", methods=["GET"])
def attest():
    """Lets a client check what kind of backend this node is actually
    running BEFORE submitting a job -- the honesty the original README's
    unconditional claims didn't give a caller any way to check."""
    claim = BACKEND.attest()
    c_w = commit_model(MODEL_PATH, VK_PATH) if os.path.exists(MODEL_PATH) else None
    return jsonify({
        "backend_kind": claim.backend_kind,
        "isolated_from_host": claim.isolated_from_host,
        "detail": claim.detail,
        "c_w": c_w,
        "audit_probability": AUDIT_PROBABILITY,
    })


@app.route("/ledger", methods=["GET"])
def ledger():
    """Exposes the append-only ledger so a client (or auditor) can
    independently verify the hash chain and confirm that the commitments
    the node sent in-band (/compute's response) match what was actually
    recorded BEFORE the challenge decision was made -- a dishonest node
    could lie in an HTTP response, but it can't rewrite a chain whose
    hashes a third party already observed."""
    return jsonify({"chain_valid": LEDGER.verify_chain(), "entries": LEDGER.entries()})


@app.route("/compute", methods=["POST"])
def compute():
    job_id = request.form.get("job_id") or request.headers.get("job-id")
    c_x = request.form.get("c_x") or request.headers.get("c-x")
    if not job_id or not c_x:
        return jsonify({"error": "job_id and c_x (input commitment) are required"}), 400

    if "ciphertext" not in request.files:
        return jsonify({"error": "Missing ciphertext"}), 400
    ciphertext = request.files["ciphertext"].read()

    key_hex = request.headers.get("decrypt-key-hex")
    if not key_hex:
        return jsonify({"error": "Missing decrypt-key-hex header"}), 400

    # --- 1. decrypt + confidential inference ---
    from cryptography.fernet import Fernet
    fkey = bytes.fromhex(key_hex)
    plaintext_bytes = Fernet(fkey).decrypt(ciphertext)
    plaintext_input = json.loads(plaintext_bytes.decode("utf-8"))

    result = BACKEND.run_confidential_inference(plaintext_input, MODEL_PATH)
    output = result.output["output"]
    witness_bytes = result.output["_witness_cache"]

    c_w = commit_model(MODEL_PATH, VK_PATH)

    # --- 2. commit to output BEFORE reading the beacon ---
    c_y, salt = commit_output(output, job_id)
    LEDGER.append("job_commit", {
        "job_id": job_id, "c_x": c_x, "c_w": c_w, "c_y": c_y,
        "backend_isolated": result.attestation.isolated_from_host,
    })

    # --- 3. only now decide whether this job is challenged ---
    beacon_round = get_beacon().latest_round()
    challenged = should_challenge(beacon_round, job_id, c_x, c_w, c_y, AUDIT_PROBABILITY)
    LEDGER.append("challenge_decision", {
        "job_id": job_id, "challenged": challenged,
        "beacon_round": beacon_round.round_number, "beacon_source": beacon_round.source,
    })

    response = {
        "job_id": job_id, "c_x": c_x, "c_w": c_w, "c_y": c_y,
        "output_salt_hex": salt.hex(),
        "challenged": challenged,
        "backend_isolated_from_host": result.attestation.isolated_from_host,
    }

    # --- 4. prove only if challenged ---
    if challenged:
        witness_path = "challenge_witness.json"
        proof_path = "challenge_proof.json"
        with open(witness_path, "wb") as f:
            f.write(witness_bytes)
        try:
            t0 = time.time()
            ok = ezkl.prove(witness_path, MODEL_PATH, PK_PATH, proof_path, SRS_PATH)
            elapsed = time.time() - t0
            if not ok:
                raise RuntimeError("ezkl.prove returned falsy")
            with open(proof_path) as f:
                proof_data = json.load(f)
            response["proof"] = proof_data
            response["prove_seconds"] = elapsed
            LEDGER.append("proof_result", {"job_id": job_id, "status": "proved", "prove_seconds": elapsed})
        finally:
            for p in (witness_path, proof_path):
                if os.path.exists(p):
                    os.remove(p)
    else:
        # Not sampled this round: output ships WITHOUT a proof. Trust here
        # comes from the economic deterrence bound (protocol/deterrence.py),
        # not from a proof -- the gateway is responsible for only paying out
        # unconditionally when the node's posted stake actually satisfies
        # S > gain/audit_probability for the job's value. See SECURITY.md.
        LEDGER.append("proof_result", {"job_id": job_id, "status": "unaudited"})

    response["output"] = output
    return jsonify(response)


def run_node(port=8000):
    backend_claim = BACKEND.attest()
    print(f"[*] Sovereign-ZK prover node starting on port {port}")
    print(f"[*] Backend: {backend_claim.backend_kind}  isolated_from_host={backend_claim.isolated_from_host}")
    if not backend_claim.isolated_from_host:
        print("[!] WARNING: running WITHOUT hardware isolation (SimulatedEnclaveBackend). "
              "Do not use for real sensitive data. See DEPLOY_NITRO.md.")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_node()
