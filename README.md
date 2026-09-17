# Sovereign-ZK

A lightweight, privacy-preserving framework for cross-border GPU compute using Zero-Knowledge Machine Learning (ZKML). Developed by **Chidiebere V. Christopher**

Sovereign-ZK allows data scientists (e.g., in Nigeria) to securely offload heavy deep learning workloads to remote GPUs (e.g., in Kenya or London) without ever exposing the plain text data to the remote host. It guarantees NDPA compliance via Trusted Execution Environments (TEEs) and cryptographic verification of the compute results using EZKL.

## Installation

```bash
pip install sovereign-zk
```

## Quick Start

### 1. Start the Remote GPU Node (London/Kenya)
On the machine with the idle GPU, run the FastAPI/Flask node to listen for encrypted payloads:

```python
from sovereign_zk.node import run_node

if __name__ == "__main__":
    # Starts the listener on port 8000
    run_node(port=8000)
```

### 2. Submit Data from the Local Client (Nigeria)
On your local machine, use the client SDK to encrypt your sensitive data, send it to the node, and cryptographically verify the returned Zero-Knowledge proof.

```python
from sovereign_zk.client import SovereignClient

# Initialize the client pointing to the remote GPU
client = SovereignClient(node_url="http://<REMOTE_NODE_IP>:8000")

# Your sensitive data
data = {"input_data": [[0.8, 0.1, 0.9, 0.2, 0.5]]}

# Encrypt the data before it leaves your machine
client.encrypt_data(data, "encrypted.bin")

# Submit the encrypted payload and the ZK circuit to the remote node
success = client.submit_compute_job(
    encrypted_data_path="encrypted.bin", 
    model_path="network.compiled", 
    pk_path="pk.key", 
    srs_path="kzg.srs", 
    output_proof_path="proof.json"
)

# Cryptographically verify the remote compute result locally
if success:
    client.verify_proof("proof.json", "settings.json", "vk.key", "kzg.srs")
```

## Architecture
This SDK forms **Phase 1** of the Sovereign-ZK deployment architecture, abstracting the complex file handling, encryption, and EZKL bindings into a simple `requests`-based HTTP workflow.

## 👤 Author

**Chidiebere V. Christopher**
* **LinkedIn**: [Chidiebere Christopher](https://www.linkedin.com/in/chidiebere-christopher/)
* **GitHub**: [93Chidiebere](https://github.com/93Chidiebere)
* **Email**: vchidiebere.vc@gmail.com