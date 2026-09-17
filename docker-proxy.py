from flask import Flask, request, jsonify
from sovereign_zk.client import SovereignClient
import json
import os

app = Flask(__name__)

# The URL of the Gateway or direct Node
REMOTE_NODE_URL = os.environ.get("REMOTE_NODE_URL", "http://gateway:5000")

@app.route("/proxy/compute", methods=["POST"])
def proxy_compute():
    """
    The local data scientist sends their plain text data to this endpoint.
    This Docker proxy completely abstracts away the cryptography.
    """
    data = request.json
    
    if not data or "input_data" not in data:
        return jsonify({"error": "Missing input_data"}), 400
        
    print("[Docker Proxy] Received raw data from local data scientist.")
    
    # 1. Initialize client and encrypt
    client = SovereignClient(node_url=REMOTE_NODE_URL)
    enc_path = "encrypted_transactions.bin"
    client.encrypt_data(data, enc_path)
    
    print("[Docker Proxy] Data encrypted. Submitting to remote node...")
    
    # 2. Submit to remote (Hardcoded local paths for the model and keys for this PoC)
    proof_path = "proof.json"
    success = client.submit_compute_job(
        enc_path, 
        "network.compiled", 
        "pk.key", 
        "kzg.srs", 
        proof_path
    )
    
    if not success:
        return jsonify({"error": "Failed to get compute result from remote"}), 502
        
    # 3. Verify locally inside the Docker container
    print("[Docker Proxy] Verifying proof...")
    is_valid = client.verify_proof(proof_path, "settings.json", "vk.key", "kzg.srs")
    
    if is_valid:
        with open(proof_path, "r") as f:
            proof_data = json.load(f)
        return jsonify({
            "status": "success",
            "message": "Data securely processed in Kenya and cryptographically verified in Nigeria.",
            "proof": proof_data
        })
    else:
        return jsonify({"error": "WARNING! Cryptographic verification failed! Result cannot be trusted."}), 403

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
