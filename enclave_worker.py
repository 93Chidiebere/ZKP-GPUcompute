import json
import os
import time

# FIX: EZKL Rust bindings on Windows panic when trying to find the default repo path
# because 'HOME' is not a native Windows environment variable (it uses USERPROFILE).
os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")

import ezkl
from cryptography.fernet import Fernet
import time

def run_enclave_worker(encrypted_data_path, key, output_proof_path, job_id):
    print(f"--- Starting Sovereign-ZK Worker Node (Job ID: {job_id}) ---")
    
    # 1. Simulating Enclave Decryption (Admin cannot see this)
    print("[*] Worker receiving encrypted payload...")
    cipher_suite = Fernet(key)
    with open(encrypted_data_path, 'rb') as f:
        encrypted_data = f.read()
    
    plaintext_data = cipher_suite.decrypt(encrypted_data)
    data = json.loads(plaintext_data.decode('utf-8'))
    
    # Save temporarily inside the "enclave" (simulated by local file)
    enclave_input_path = f"enclave_input_{job_id}.json"
    with open(enclave_input_path, "w") as f:
        json.dump(data, f)
    print("[+] Worker decrypted transaction data internally.")

    # 2. Run ZKML Proving
    compiled_model_path = "network.compiled"
    pk_path = "pk.key"
    srs_path = "kzg.srs"
    settings_path = "settings.json"
    
    witness_path = f"witness_{job_id}.json"
    print("[*] Generating cryptographic witness from data...")
    ezkl.gen_witness(enclave_input_path, compiled_model_path, witness_path)
    
    print(f"[*] Executing Deep Learning Inference & Generating ZK Proof...")
    start_time = time.time()
    
    # Generate a proof
    res = ezkl.prove(
        witness_path,
        compiled_model_path,
        pk_path,
        output_proof_path,
        "single",
        srs_path
    )
    
    end_time = time.time()
    print(f"[+] Zero-Knowledge Proof generated in {end_time - start_time:.2f} seconds.")
    print(f"[+] Proof saved to {output_proof_path}")
    
    # 3. Secure Cleanup (Simulating ephemeral enclave memory)
    os.remove(enclave_input_path)
    os.remove(witness_path)
    print("--- Worker Execution Complete. Returning Proof to Relayer ---")
    
    return output_proof_path

if __name__ == "__main__":
    # For testing the script standalone
    pass
