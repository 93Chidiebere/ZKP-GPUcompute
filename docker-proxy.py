"""
Local convenience proxy: accepts plaintext JSON from a data scientist on
localhost and runs it through the real commit-then-challenge client flow
(client_demo.run_job), instead of the deprecated SovereignClient.

Fix from the original: the old version reported success as soon as
`verify_proof()` passed -- but verify_proof was only ever called when a
proof existed, and under the probabilistic-audit design MOST jobs won't
have one (that's the entire point of sampling). This version reports
accurately whether a given job was cryptographically verified or accepted
on stake-backed trust, instead of implying every response is proof-backed.
"""
import os

from flask import Flask, request, jsonify

from client_demo import run_job, load_registered_model_commitment

app = Flask(__name__)

NODE_URL = os.environ.get("REMOTE_NODE_URL", "http://127.0.0.1:8000")


@app.route("/proxy/compute", methods=["POST"])
def proxy_compute():
    data = request.json
    if not data or "input_data" not in data:
        return jsonify({"error": "Missing input_data"}), 400

    try:
        registered_c_w = load_registered_model_commitment()
    except FileNotFoundError:
        return jsonify({"error": "model_commitment.json not found -- run model_setup.py first"}), 500

    result = run_job(NODE_URL, data, registered_c_w)
    if result is None:
        return jsonify({"error": "Job failed: model mismatch, ledger mismatch, or proof verification failed. See server logs."}), 502

    return jsonify({
        "status": "success",
        "output": result["output"],
        "cryptographically_verified": bool(result["challenged"]),
        "backend_isolated_from_host": result["backend_isolated_from_host"],
        "message": (
            "Proof was generated and independently verified for this job."
            if result["challenged"] else
            "This job was not sampled for a ZK proof; accepted on the node's "
            "posted economic stake, not on cryptographic proof of this specific inference."
        ),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
