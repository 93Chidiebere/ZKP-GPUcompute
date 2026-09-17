import json
import os
from cryptography.fernet import Fernet
import time

# FIX: EZKL Rust bindings on Windows panic when trying to find the default repo path
# because 'HOME' is not a native Windows environment variable (it uses USERPROFILE).
os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")

import ezkl
from kenya_enclave_server import run_kenya_enclave

def main():
    print("=== SOVEREIGN-ZK CLIENT (Lagos, Nigeria) ===")
    
    # 1. Prepare Data
    print("[*] Preparing batch of sensitive financial transactions...")
    # Dummy data (1 sample, 5 features)
    dummy_input = [[0.8, 0.1, 0.9, 0.2, 0.5]]
    data_dict = {"input_data": dummy_input}
    
    # 2. Encrypt Data (Before leaving Nigeria)
    print("[*] Encrypting data for transport to Kenya...")
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    
    plaintext = json.dumps(data_dict).encode('utf-8')
    encrypted_data = cipher_suite.encrypt(plaintext)
    
    encrypted_data_path = "encrypted_transactions.bin"
    with open(encrypted_data_path, "wb") as f:
        f.write(encrypted_data)
        
    print(f"[+] Data securely encrypted and saved to {encrypted_data_path}")
    
    print("\n--- INITIATING CROSS-BORDER COMPUTE ---")
    proof_path = "proof.json"
    
    # 3. Simulate sending to Kenya and receiving the proof
    # In a real app, this would be an HTTP POST request to the Kenyan IP
    run_kenya_enclave(encrypted_data_path, key, proof_path)
    
    print("\n=== RECEIVING RESULTS IN NIGERIA ===")
    # 4. Verify the ZK Proof
    print("[*] Verifying cryptographic proof from Kenya...")
    compiled_model_path = "network.compiled"
    vk_path = "vk.key"
    settings_path = "settings.json"
    srs_path = "kzg.srs"
    
    start_verify = time.time()
    
    is_valid = ezkl.verify(
        proof_path,
        settings_path,
        vk_path,
        srs_path
    )
    
    end_verify = time.time()
    
    if is_valid:
        print(f"[SUCCESS] Proof cryptographically verified in {end_verify - start_verify:.4f} seconds!")
        print("[SUCCESS] The Nigerian bank can 100% trust the result. NDPA Compliance maintained.")
    else:
        print("[ERROR] Proof verification failed! The remote node tampered with the model or data.")

if __name__ == "__main__":
    main()
