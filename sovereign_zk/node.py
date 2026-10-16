import os
import json
import time
import hashlib

def main():
    print("--- [KENYA NODE] Sovereign-ZK SLA Node ---")
    print("[*] Listening for new AI Compute Jobs (Off-Chain)...")

    while True:
        if os.path.exists("network_state.json"):
            with open("network_state.json", "r") as f:
                try:
                    state = json.load(f)
                except json.JSONDecodeError:
                    continue # Wait for write to finish
                    
            status = state.get("status")
            
            if status == "pending_inference":
                job_id = state.get("job_id")
                c_x = state.get("c_x")
                print(f"\n[+] New Job Detected! Job ID: {job_id}")
                
                # 1. Simulate TEE Decryption and Inference
                print("[*] Enclave isolating memory...")
                print("[*] Executing Deep Learning Inference (FP16)...")
                time.sleep(2)
                
                mock_output = b"Fraud_Score: 0.12"
                
                # 2. Generate Output Commitment (C_y) over (JobID, C_x, Output)
                commitment_input = job_id.encode() + c_x.encode() + mock_output
                c_y = hashlib.sha256(commitment_input).hexdigest()
                print(f"[+] Committing to (JobID, C_x, Output) -> C_y: {c_y}")
                
                state["status"] = "committed"
                state["c_y"] = c_y
                with open("network_state.json", "w") as f:
                    json.dump(state, f)
                    
            elif status == "challenged":
                print(f"\n[!] ALERT: Randomness Beacon selected Job {state['job_id']} for Audit!")
                
                # 1. Receive plaintext (X, nonce) from client to prove inside circuit
                nonce = state.get("nonce")
                print("[*] Client revealed input nonces. Preparing ZK-SNARK Proving Circuit...")
                
                # 2. Generate Proof
                print("[*] Generating halo2 ZK-SNARK Proof (Warning: High Compute Overhead)...")
                time.sleep(4)
                
                proof = "0xABC123_VALID_ZK_PROOF"
                
                state["status"] = "proof_submitted"
                state["proof"] = proof
                with open("network_state.json", "w") as f:
                    json.dump(state, f)
                    
                print("[+] Proof submitted successfully. Awaiting SLA payout.")
                
        time.sleep(1)

if __name__ == "__main__":
    main()
