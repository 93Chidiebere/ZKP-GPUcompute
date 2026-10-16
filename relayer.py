import os
import json
import time
from web3 import Web3
from enclave_worker import run_enclave_worker

# Dummy Configuration for Local Testing
RPC_URL = "http://127.0.0.1:8545" # e.g. Anvil or Hardhat
CONTRACT_ADDRESS = "0x0000000000000000000000000000000000000000" # Replace with actual deployed InferenceMarket
PRIVATE_KEY = "0x0000000000000000000000000000000000000000000000000000000000000000" # Replace

# Minimal ABI for listening to events and submitting proof
INFERENCE_MARKET_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "jobId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "requester", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "dataUri", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "reward", "type": "uint256"}
        ],
        "name": "InferenceRequested",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "jobId", "type": "uint256"},
            {"internalType": "bytes", "name": "proof", "type": "bytes"},
            {"internalType": "uint256[]", "name": "instances", "type": "uint256[]"}
        ],
        "name": "submitProof",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def handle_new_job(event, web3, contract):
    job_id = event['args']['jobId']
    data_uri = event['args']['dataUri']
    reward = event['args']['reward']
    
    print(f"\n[+] New Inference Job Detected! Job ID: {job_id}, Reward: {reward}")
    print(f"[*] Data URI: {data_uri}")
    
    # In a real app, data_uri would be IPFS hash or S3 bucket.
    # We will assume data_uri points to our local encrypted file for the MVP.
    encrypted_data_path = data_uri if os.path.exists(data_uri) else "encrypted_transactions.bin"
    
    # In MVP, key management is out of scope. We'll use a hardcoded testing key.
    # Usually this is managed by AWS KMS via the Enclave.
    testing_key = b'0123456789abcdef0123456789abcdef0123456789a=' # MUST be 32 url-safe base64
    
    output_proof_path = f"proof_job_{job_id}.json"
    
    try:
        # 1. Run the Worker Node (ZKML Inference)
        proof_file = run_enclave_worker(encrypted_data_path, testing_key, output_proof_path, job_id)
        
        # 2. Parse Proof
        with open(proof_file, "r") as f:
            proof_data = json.load(f)
            
        # EZKL outputs hex strings. We need to convert to bytes and uint256 array
        proof_bytes = bytes.fromhex(proof_data["proof"].replace("0x", ""))
        # For MVP, instances are often empty or a single array of inputs/outputs depending on public visibility.
        # Check if instances exist, else pass empty.
        instances_raw = proof_data.get("instances", [])
        instances = []
        for inst_array in instances_raw:
            for val in inst_array:
                # Convert hex to int
                instances.append(int(val, 16) if isinstance(val, str) else val)

        print(f"[*] Submitting Proof for Job {job_id} to Blockchain...")
        
        # 3. Submit Transaction
        account = web3.eth.account.from_key(PRIVATE_KEY)
        nonce = web3.eth.get_transaction_count(account.address)
        
        tx = contract.functions.submitProof(job_id, proof_bytes, instances).build_transaction({
            'from': account.address,
            'nonce': nonce,
            # 'gas': 3000000, # Let it estimate
            'gasPrice': web3.eth.gas_price
        })
        
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"[+] Transaction Sent! Hash: {tx_hash.hex()}")
        
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"[+] Proof Verified and Reward Claimed! Block: {receipt.blockNumber}")
        
    except Exception as e:
        print(f"[!] Error processing job {job_id}: {e}")

def main():
    print("--- Starting Sovereign-ZK Relayer ---")
    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    if not web3.is_connected():
        print("[!] Could not connect to Web3 Provider. Waiting for node...")
        return

    contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=INFERENCE_MARKET_ABI)
    
    # We will poll for new events.
    # A real production relayer would use WebSocket wss:// and subscriptions.
    print("[*] Listening for InferenceRequested events on the blockchain...")
    
    last_block_checked = web3.eth.block_number
    
    try:
        while True:
            current_block = web3.eth.block_number
            if current_block > last_block_checked:
                event_filter = contract.events.InferenceRequested.create_filter(fromBlock=last_block_checked+1, toBlock=current_block)
                for event in event_filter.get_new_entries():
                    handle_new_job(event, web3, contract)
                last_block_checked = current_block
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[*] Relayer stopped.")

if __name__ == "__main__":
    main()
