# Sovereign-ZK

Sovereign-ZK is an early-stage research prototype for privacy-preserving remote AI compute with dispute-triggered verifiable execution.

## Security status: prototype only

**Do not submit personal, health, financial, confidential, or otherwise sensitive data to this release.** The current remote node is ordinary Python. The demo encrypts data with Fernet, then sends the Fernet key to the same remote node. The node can decrypt and read the plaintext. It does not use an attested TEE, and its EZKL proof is generated for every job.

The package does not currently provide end-to-end confidentiality, a production dispute mechanism, enforceable staking/slashing, or a guarantee of compliance with the Nigeria Data Protection Act. An EZKL proof can establish only the computation encoded by the circuit and its public inputs. It does not prove use of a particular GPU, correct model design, clinical validity, or legal compliance.

The default client and node now refuse this insecure demo flow. It can be enabled only for synthetic data with explicit opt-in (see below).

## Target protocol

The research direction is a commit-then-dispute protocol:

1. The client and provider agree on the exact model or training-program commitment, input commitment, output format, deadline, and service terms.
2. Before any dispute, the provider returns a salted commitment to the claimed output. The commitment must be fixed before a challenge can be raised.
3. During a defined challenge window, the client may dispute the result. The client re-supplies the input and commitment nonce through an attested execution environment.
4. For a challenged job, the provider must prove in zero knowledge that the committed model/program, input, and output satisfy the specified relation. The proof verifier checks the exact commitments from step 1 and 2.
5. A valid proof resolves the dispute in the provider's favor. Failure to prove by the deadline is eligible for a penalty under an enforceable service contract or bond.

A challenged proof must be bound to the original commitments; a provider must not be able to replace a disputed output with a corrected one. A proof establishes computation correctness for the encoded relation. It does not prove that work happened at the original time or on a GPU. The deadline and service terms must account for the possibility of computing after a challenge.

The in-memory state machine in `sovereign_zk/protocol.py` sketches these transitions. It is not connected to the HTTP node, EZKL, durable storage, hardware attestation, a bond, or a smart contract. It is a protocol scaffold, not a security control.

## Privacy architecture needed before sensitive use

Sensitive workloads require an actual confidential-computing design. At minimum, that means hardware-backed remote attestation, authenticated key release only to an approved enclave measurement, protected data movement to any GPU, memory and temporary-file controls, output minimization, and a stated hardware-vendor threat model. A TEE reduces trust in the host operator but retains trust in the hardware, firmware, attestation service, and implementation.

A TEE does not by itself establish compliance with Nigerian data-protection requirements. Controllers and processors still need an appropriate legal basis, transfer safeguards where applicable, contracts, retention controls, and organizational governance, reviewed for the specific deployment.

## Running the synthetic-data demo

The current demo exposes the encryption key to the remote node and runs outside a TEE. Use synthetic data only. To opt in on the client:

```python
client = SovereignClient(
    node_url="http://127.0.0.1:8000",
    allow_insecure_demo=True,
)
```

To enable the demo endpoint, set `SOVEREIGN_ZK_ALLOW_INSECURE_DEMO=1` in the node environment. Do not expose this demo node to the public internet. The opt-in is a guardrail, not a security feature.

## Research questions

- Can dispute-triggered proof generation meet a useful deadline and cost target for realistic inference and training workloads?
- What commitment and proof relation binds the agreed code/model, input, output, and configuration?
- What challenge policy and penalty make cheating unprofitable without making honest service uneconomic?
- How should the design handle unavailable clients, output leakage, side channels, prover denial of service, and cross-border enforcement?
- What deployment safeguards are required for each workload under applicable data-protection law?

## References and scope

The protocol combines confidential computing with verifiable computation and mechanism design. Sampling-based audits and TEE/ZK combinations have prior art; any novelty claim must be established against that literature. The claimed “Localized Externality Bound” is a proposed analysis, not a proven result in this repository. Claims that optimistic verification categorically fails on encrypted data should be narrowed to a precise threat model and verifier/data-availability assumption.

This project is an academic prototype and is not legal advice. Consult qualified Nigerian data-protection counsel before processing personal data or transferring it across borders.
