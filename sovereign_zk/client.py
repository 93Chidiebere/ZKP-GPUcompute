import os
import json
import time
import requests
from cryptography.fernet import Fernet

# FIX: EZKL Rust bindings on Windows panic when trying to find the default repo path
os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\")
import ezkl

class SovereignClient:
    def __init__(self, node_url: str):
        self.node_url = node_url
        self.fernet_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.fernet_key)

    def encrypt_data(self, data: dict, output_path: str):
        plaintext = json.dumps(data).encode('utf-8')
        encrypted_data = self.cipher_suite.encrypt(plaintext)
        with open(output_path, "wb") as f:
            f.write(encrypted_data)
        return output_path

    def submit_compute_job(self, encrypted_data_path: str, model_path: str, pk_path: str, srs_path: str, output_proof_path: str):
        print(f"[*] Sending data to remote node at {self.node_url}...")
        
        headers = {
            "fernet-key": self.fernet_key.decode('utf-8')
        }
        
        with open(encrypted_data_path, "rb") as ed, \
             open(model_path, "rb") as cm, \
             open(pk_path, "rb") as pk, \
             open(srs_path, "rb") as srs:
            
            files = {
                "encrypted_data": ed,
                "compiled_model": cm,
                "pk_key": pk,
                "kzg_srs": srs
            }
            
            try:
                response = requests.post(f"{self.node_url}/compute", files=files, headers=headers)
                
                if response.status_code != 200:
                    print(f"[ERROR] Node returned {response.status_code}: {response.text}")
                    return False
                    
                proof_data = response.json()
                with open(output_proof_path, "w") as f:
                    json.dump(proof_data, f)
                    
                print(f"[+] Received proof from remote node and saved to {output_proof_path}")
                return True
            except Exception as e:
                print(f"[ERROR] Connection failed: {e}")
                return False

    def verify_proof(self, proof_path: str, settings_path: str, vk_path: str, srs_path: str):
        print("[*] Verifying cryptographic proof locally...")
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
            return True
        else:
            print("[ERROR] Proof verification failed!")
            return False

def test_client():
    print("=== SOVEREIGN-ZK CLIENT (Lagos, Nigeria) ===")
    
    # 1. Prepare Data
    print("[*] Preparing batch of sensitive financial transactions...")
    dummy_input = [[0.8, 0.1, 0.9, 0.2, 0.5]]
    data_dict = {"input_data": dummy_input}
    
    client = SovereignClient(node_url="http://127.0.0.1:8000")
    
    # 2. Encrypt Data
    enc_path = "encrypted_transactions.bin"
    client.encrypt_data(data_dict, enc_path)
    print(f"[+] Data securely encrypted.")
    
    # 3. Submit to Node
    proof_path = "proof.json"
    success = client.submit_compute_job(
        enc_path, 
        "network.compiled", 
        "pk.key", 
        "kzg.srs", 
        proof_path
    )
    
    if success:
        # 4. Verify
        client.verify_proof(proof_path, "settings.json", "vk.key", "kzg.srs")

if __name__ == "__main__":
    test_client()
