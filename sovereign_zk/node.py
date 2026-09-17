import os
import json
import time
from flask import Flask, request, jsonify
from cryptography.fernet import Fernet

os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")
import ezkl

app = Flask(__name__)

@app.route("/compute", methods=["POST"])
def compute_proof():
    print("--- [KENYA NODE] New Compute Job Received ---")
    
    if "encrypted_data" not in request.files:
        return jsonify({"error": "Missing encrypted_data"}), 400
        
    fernet_key = request.headers.get("fernet-key")
    if not fernet_key:
        return jsonify({"error": "Missing fernet-key header"}), 400
        
    data_path = "temp_encrypted.bin"
    model_path = "temp_network.compiled"
    pk_path = "temp_pk.key"
    srs_path = "temp_kzg.srs"
    
    request.files["encrypted_data"].save(data_path)
    request.files["compiled_model"].save(model_path)
    request.files["pk_key"].save(pk_path)
    request.files["kzg_srs"].save(srs_path)
    
    print("[*] Enclave receiving encrypted payload...")
    
    try:
        cipher_suite = Fernet(fernet_key.encode('utf-8'))
        with open(data_path, "rb") as f:
            encrypted_bytes = f.read()
        plaintext = cipher_suite.decrypt(encrypted_bytes)
        data_dict = json.loads(plaintext.decode('utf-8'))
        print("[+] Enclave decrypted transaction data internally.")
    except Exception as e:
        return jsonify({"error": f"Decryption failed: {str(e)}"}), 400

    enclave_input_path = "temp_enclave_input.json"
    with open(enclave_input_path, "w") as f:
        json.dump(data_dict, f)

    witness_path = "temp_witness.json"
    output_proof_path = "temp_proof.json"
    
    print("[*] Generating cryptographic witness from data...")
    ezkl.gen_witness(enclave_input_path, model_path, witness_path)
    
    print("[*] Executing Deep Learning Inference & Generating ZK Proof...")
    start_prove = time.time()
    res = ezkl.prove(witness_path, model_path, pk_path, output_proof_path, "single", srs_path)
    end_prove = time.time()
    
    print(f"[+] Zero-Knowledge Proof generated in {end_prove - start_prove:.2f} seconds.")
    
    if not res:
        return jsonify({"error": "Failed to generate proof"}), 500

    with open(output_proof_path, "r") as f:
        proof_data = json.load(f)
        
    return jsonify(proof_data)

def run_node(port=8000):
    print(f"[*] Sovereign-ZK Node running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    run_node()
