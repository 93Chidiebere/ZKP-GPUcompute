"""
Gateway (escrow + settlement).

Fixes from the original prototype, per the round-2 review (A1, A6, A7):

  1. OLD: Paystack *split* payment paid 90% to the node at CHARGE time, with
     the proof generated afterward. Payment was never actually conditional
     on anything -- the node got paid whether or not the compute was
     correct.
     NEW: the gateway charges the client's FULL amount to the platform's
     own account (no split). The node is paid via a SEPARATE Paystack
     Transfer call, issued only after settlement logic below decides the
     node earned it. A failed challenge triggers a Refund, not a Transfer.

  2. OLD: no stake, no slashing, no check that a node could ever lose money
     by cheating. The deterrence bound (S > g/q) was pure math no code
     enforced.
     NEW: NODE_REGISTRY tracks a posted `staked_ngn` per node. Before
     routing a job, the gateway checks that the node's stake actually
     satisfies the deterrence bound for that job's value
     (protocol/deterrence.py). A challenge failure records a slashing
     event in the local ledger and reduces the node's effective stake --
     this is bookkeeping, not an on-chain guarantee (see ledger.py's
     honesty note: a dishonest OPERATOR of this gateway could still edit
     the stake number; the hash chain only protects against a dishonest
     NODE, not a dishonest gateway operator. A production deployment needs
     the stake itself held somewhere the gateway operator can't unilaterally
     move, e.g. an actual escrow contract).

  3. Settlement for NON-challenged jobs (the 99% case) is release-on-stake,
     not release-on-proof -- that's the entire point of sampling. This is
     now explicit in code (see `settle()`) instead of being an unstated
     assumption.
"""

from __future__ import annotations

import os
import time

import requests
from flask import Flask, request, jsonify

from sovereign_zk.protocol.deterrence import required_stake, expected_profit_from_cheating
from sovereign_zk.protocol.ledger import Ledger

app = Flask(__name__)

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_dummy_key_123456789")
PAYSTACK_BASE = "https://api.paystack.co"
AUDIT_PROBABILITY_DEFAULT = float(os.environ.get("SOVEREIGN_ZK_AUDIT_PROBABILITY", "0.01"))

LEDGER = Ledger(os.environ.get("SOVEREIGN_ZK_GATEWAY_LEDGER_PATH", "gateway_ledger.jsonl"))

# In a real system nodes register dynamically and post a real stake (e.g.
# into an escrow account / contract this gateway doesn't unilaterally
# control). Hardcoded here for the single local PoC node -- staked_ngn is a
# BOOKKEEPING number this gateway trusts itself on; see the module
# docstring for why that's not yet a real trust-minimized guarantee.
NODE_REGISTRY = {
    "node_kenya_01": {
        "url": "http://127.0.0.1:8000",
        "paystack_recipient_code": os.environ.get("NODE_PAYSTACK_RECIPIENT_CODE", "RCP_dummy_recipient_code"),
        "staked_ngn": float(os.environ.get("NODE_STAKED_NGN", "0")),
    }
}


def _paystack_headers():
    return {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}


@app.route("/api/v1/job/initialize", methods=["POST"])
def initialize_job():
    """Charges the FULL amount to the platform's own account (no split).
    Settlement to the node happens later, conditionally, in settle()."""
    data = request.json or {}
    email = data.get("email")
    amount_ngn = data.get("amount_ngn", 5000)
    target_node = data.get("target_node", "node_kenya_01")

    if target_node not in NODE_REGISTRY:
        return jsonify({"error": "Unknown node"}), 400

    node = NODE_REGISTRY[target_node]
    stake_check = required_stake(gain_per_cheat=amount_ngn, audit_probability=AUDIT_PROBABILITY_DEFAULT)
    if node["staked_ngn"] < stake_check.minimum_stake:
        return jsonify({
            "error": "Node is under-staked for a job of this value.",
            "node_staked_ngn": node["staked_ngn"],
            "minimum_required_stake_ngn": stake_check.minimum_stake,
            "detail": "Per the deterrence bound S > g/q, a node must stake more than "
                      f"{stake_check.minimum_stake:.2f} NGN to be trusted with a "
                      f"{amount_ngn} NGN job at audit_probability={AUDIT_PROBABILITY_DEFAULT}.",
        }), 409

    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json={
                "email": email,
                "amount": amount_ngn * 100,  # kobo
                "callback_url": data.get("callback_url", "http://localhost:5000/api/v1/job/callback"),
            },
            headers=_paystack_headers(), timeout=15,
        )
        pdata = resp.json()
    except Exception as e:
        return jsonify({"error": f"Failed to contact Paystack: {e}"}), 502

    if not pdata.get("status"):
        return jsonify({"error": pdata.get("message")}), 400

    LEDGER.append("job_commit", {
        "reference": pdata["data"]["reference"], "target_node": target_node,
        "amount_ngn": amount_ngn,
    })
    return jsonify({
        "message": "Payment initialized to platform account. Node is paid separately after settlement.",
        "checkout_url": pdata["data"]["authorization_url"],
        "reference": pdata["data"]["reference"],
    })


def _verify_payment(reference: str) -> bool:
    resp = requests.get(f"{PAYSTACK_BASE}/transaction/verify/{reference}", headers=_paystack_headers(), timeout=15)
    data = resp.json()
    return bool(data.get("status")) and data.get("data", {}).get("status") == "success"


def _paystack_transfer(recipient_code: str, amount_ngn: float, reason: str):
    return requests.post(
        f"{PAYSTACK_BASE}/transfer",
        json={"source": "balance", "amount": int(amount_ngn * 100), "recipient": recipient_code, "reason": reason},
        headers=_paystack_headers(), timeout=15,
    ).json()


def _paystack_refund(reference: str, reason: str):
    return requests.post(
        f"{PAYSTACK_BASE}/refund",
        json={"transaction": reference, "merchant_note": reason},
        headers=_paystack_headers(), timeout=15,
    ).json()


@app.route("/api/v1/job/execute", methods=["POST"])
def execute_job():
    """Verifies payment, forwards the job to the node's real /compute
    endpoint (job_id/c_x/ciphertext -- see prover_node.py), then settles."""
    reference = request.form.get("reference")
    target_node = request.form.get("target_node", "node_kenya_01")
    job_id = request.form.get("job_id")
    c_x = request.form.get("c_x")
    amount_ngn = float(request.form.get("amount_ngn", 5000))

    if not reference or not job_id or not c_x:
        return jsonify({"error": "Missing reference, job_id, or c_x"}), 400
    if target_node not in NODE_REGISTRY:
        return jsonify({"error": "Unknown node"}), 400
    if "ciphertext" not in request.files:
        return jsonify({"error": "Missing ciphertext"}), 400

    if not _verify_payment(reference):
        return jsonify({"error": "Payment not verified or incomplete."}), 402

    node = NODE_REGISTRY[target_node]
    fkey_hex = request.headers.get("decrypt-key-hex")

    try:
        node_resp = requests.post(
            f"{node['url']}/compute",
            data={"job_id": job_id, "c_x": c_x},
            files={"ciphertext": request.files["ciphertext"].read()},
            headers={"decrypt-key-hex": fkey_hex},
            timeout=180,  # proving can take well over a minute; see SECURITY.md benchmark
        )
    except Exception as e:
        return jsonify({"error": f"Failed to contact node: {e}"}), 502

    if node_resp.status_code != 200:
        return jsonify({"error": f"Node failed: {node_resp.text}"}), 502

    result = node_resp.json()
    settlement = settle(target_node, reference, job_id, amount_ngn, result)
    result["settlement"] = settlement
    return jsonify(result)


def settle(target_node: str, reference: str, job_id: str, amount_ngn: float, node_result: dict) -> dict:
    """The function the round-2 review's A1 said didn't exist: what
    actually determines payment.

      - challenged + proof present but INVALID verification is the node's
        responsibility to self-report honestly; a production system must
        have the CLIENT (or gateway, as a semi-trusted verifier here)
        independently run ezkl.verify before trusting `result['proof']`.
        This gateway does so below rather than trusting the node's say-so.
      - challenged + proof verifies -> pay the node, platform keeps a 10%
        fee.
      - challenged + proof does NOT verify -> refund the client, record a
        slashing event, reduce the node's bookkeeping stake.
      - not challenged -> pay the node (this is the "cheap for 99% of
        jobs" case the whole audit design exists to enable -- it is safe
        ONLY because of the stake check already performed in
        initialize_job(), not because anything was proven for this
        specific job).
    """
    node = NODE_REGISTRY[target_node]
    payout_share = 0.90

    if node_result.get("challenged"):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            proof_path = os.path.join(d, "proof.json")
            with open(proof_path, "w") as f:
                _json.dump(node_result["proof"], f)
            os.environ.setdefault("HOME", "/tmp")
            import ezkl
            valid = ezkl.verify(proof_path, "settings.json", "vk.key", "kzg.srs")

        if not valid:
            refund = _paystack_refund(reference, f"Sovereign-ZK: challenged proof failed verification (job {job_id})")
            node["staked_ngn"] = max(0.0, node["staked_ngn"] - amount_ngn)  # slash
            LEDGER.append("settlement", {
                "job_id": job_id, "outcome": "SLASHED_REFUND", "amount_ngn": amount_ngn,
                "node_staked_ngn_after": node["staked_ngn"], "paystack_refund": refund,
            })
            return {"outcome": "SLASHED_REFUND", "node_staked_ngn_after": node["staked_ngn"]}

        transfer = _paystack_transfer(node["paystack_recipient_code"], amount_ngn * payout_share,
                                       f"Sovereign-ZK: verified job {job_id}")
        LEDGER.append("settlement", {"job_id": job_id, "outcome": "PAID_VERIFIED", "amount_ngn": amount_ngn,
                                      "paystack_transfer": transfer})
        return {"outcome": "PAID_VERIFIED"}

    # not challenged: pay on stake, per the deterrence model
    transfer = _paystack_transfer(node["paystack_recipient_code"], amount_ngn * payout_share,
                                   f"Sovereign-ZK: unaudited job {job_id} (stake-backed)")
    LEDGER.append("settlement", {"job_id": job_id, "outcome": "PAID_UNAUDITED_STAKE_BACKED",
                                  "amount_ngn": amount_ngn, "paystack_transfer": transfer})
    return {"outcome": "PAID_UNAUDITED_STAKE_BACKED"}


@app.route("/api/v1/node/stake", methods=["POST"])
def post_stake():
    """Minimal stand-in for an operator posting/topping-up a node's stake.
    A real deployment would verify this against an actual held deposit
    (escrow account, on-chain bond, etc.), not accept a number over HTTP."""
    data = request.json or {}
    node_id = data.get("node_id")
    amount_ngn = float(data.get("amount_ngn", 0))
    if node_id not in NODE_REGISTRY:
        return jsonify({"error": "Unknown node"}), 400
    NODE_REGISTRY[node_id]["staked_ngn"] += amount_ngn
    LEDGER.append("stake_posted", {"node_id": node_id, "amount_ngn": amount_ngn,
                                    "new_total_ngn": NODE_REGISTRY[node_id]["staked_ngn"]})
    return jsonify({"node_id": node_id, "staked_ngn": NODE_REGISTRY[node_id]["staked_ngn"]})


if __name__ == "__main__":
    print("[*] Sovereign-ZK Gateway starting on port 5000...")
    print("[!] PAYSTACK_SECRET_KEY is", "a TEST/DUMMY key -- Paystack calls will fail" if "dummy" in PAYSTACK_SECRET_KEY else "configured")
    app.run(host="0.0.0.0", port=5000, debug=False)
