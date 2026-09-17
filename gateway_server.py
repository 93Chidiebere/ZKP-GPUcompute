import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Replace this with your actual Paystack Secret Key later
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_dummy_key_123456789")

# In a real system, nodes would register dynamically.
# We hardcode the Node ID to our local Flask node for the PoC.
REGISTERED_NODES = {
    "node_kenya_01": {
        "url": "http://127.0.0.1:8000",
        "paystack_subaccount_code": "ACCT_dummy_subaccount_code" # The Compute Owner's Paystack Subaccount
    }
}

@app.route("/api/v1/job/initialize", methods=["POST"])
def initialize_job():
    """
    Step 1: The data scientist wants to run a job. We calculate the cost and 
    generate a Paystack payment link using Split Payments.
    """
    data = request.json
    email = data.get("email")
    amount_ngn = data.get("amount_ngn", 5000) # Default to 5000 NGN for the compute job
    target_node = data.get("target_node", "node_kenya_01")
    
    if target_node not in REGISTERED_NODES:
        return jsonify({"error": "Unknown node"}), 400
        
    node_info = REGISTERED_NODES[target_node]
    
    # Paystack Split Payment API call
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    paystack_payload = {
        "email": email,
        "amount": amount_ngn * 100, # Paystack expects amount in kobo
        "split": {
            "type": "percentage",
            "bearer": "subaccount",
            "subaccounts": [
                {
                    "subaccount": node_info["paystack_subaccount_code"],
                    "share": 90 # 90% goes to the compute owner (friend in Kenya)
                }
            ]
            # The remaining 10% automatically stays in the main account (the Platform Fee)
        },
        "callback_url": "http://localhost:5000/api/v1/job/callback"
    }
    
    try:
        response = requests.post(
            "https://api.paystack.co/transaction/initialize", 
            json=paystack_payload, 
            headers=headers
        )
        paystack_data = response.json()
        
        if paystack_data.get("status"):
            return jsonify({
                "message": "Payment initialized. 90% goes to compute owner, 10% platform fee.",
                "checkout_url": paystack_data["data"]["authorization_url"],
                "reference": paystack_data["data"]["reference"]
            })
        else:
            return jsonify({"error": paystack_data.get("message")}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to connect to Paystack: {str(e)}"}), 500

@app.route("/api/v1/job/execute", methods=["POST"])
def execute_job():
    """
    Step 2: After payment is made, the data scientist submits the data along with the payment reference.
    We verify the payment with Paystack, and if successful, route the data to the node.
    """
    reference = request.form.get("reference")
    target_node = request.form.get("target_node", "node_kenya_01")
    
    if not reference:
        return jsonify({"error": "Missing payment reference"}), 400
        
    # Verify transaction with Paystack
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    
    try:
        verify_res = requests.get(verify_url, headers=headers).json()
        if not verify_res.get("status") or verify_res["data"]["status"] != "success":
            return jsonify({"error": "Payment not verified or incomplete."}), 402
    except Exception as e:
        return jsonify({"error": f"Verification error: {str(e)}"}), 500
        
    print(f"[+] Payment {reference} verified successfully! Routing job to {target_node}...")
    
    # Extract files
    if "encrypted_data" not in request.files:
        return jsonify({"error": "Missing encrypted_data"}), 400
        
    # Route job to the actual Node
    node_url = REGISTERED_NODES[target_node]["url"]
    fernet_key = request.headers.get("fernet-key")
    
    node_headers = {"fernet-key": fernet_key}
    
    files = {
        "encrypted_data": request.files["encrypted_data"].read(),
        "compiled_model": request.files["compiled_model"].read(),
        "pk_key": request.files["pk_key"].read(),
        "kzg_srs": request.files["kzg_srs"].read()
    }
    
    print(f"[*] Proxying data to remote node at {node_url}...")
    
    try:
        node_response = requests.post(f"{node_url}/compute", files=files, headers=node_headers)
        
        if node_response.status_code == 200:
            print("[+] Node returned ZK Proof successfully.")
            return jsonify(node_response.json())
        else:
            return jsonify({"error": f"Node failed: {node_response.text}"}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to contact node: {str(e)}"}), 502

if __name__ == "__main__":
    print("[*] Sovereign-ZK Managed Gateway starting on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=True)
