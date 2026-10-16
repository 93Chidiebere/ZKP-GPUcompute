# Security status

This document exists because earlier versions of this repo's README and
console output claimed things the code did not do ("AWS Nitro Enclave",
"Admin cannot see this", "NDPA Compliance maintained") while running in an
ordinary, unisolated Python process that wrote plaintext to disk. This file
is the honest version: what's real today, what requires real hardware you
must deploy yourself, and what's still just a design.

## Status matrix

| Property | SimulatedEnclaveBackend (default, this repo) | NitroEnclaveBackend (written, needs real AWS deployment) |
|---|---|---|
| Hardware isolation from host | **No.** Ordinary process. | Yes, if deployed per `DEPLOY_NITRO.md` -- backed by AWS attestation + KMS key policy, not by this Python code alone. |
| Plaintext ever on persistent disk | No (uses `/dev/shm`, tmpfs, RAM-backed) with guaranteed cleanup in `finally` | N/A -- same tmpfs pattern, but irrelevant once real isolation exists |
| `attest()` claims it's isolated | **No** -- explicitly reports `isolated_from_host: False` | Yes, and fails closed (raises) if `/dev/nsm` is absent, i.e. it refuses to lie by running outside an enclave |
| Suitable for real sensitive data | **No.** Protocol development / testing only. | Only after a real deployment with a correctly scoped KMS key policy |

## What's cryptographically real right now

- EZKL circuit compilation, witness generation, proving, and verification
  (`model_setup.py`, `prover_node.py`, `client_demo.py`) run real `ezkl`
  calls against a real (if small, synthetic-data) trained model -- not a
  zero-weight placeholder.
- Measured on this development machine's CPU: proving a 5→16→1 MLP took
  **74.4 seconds**; verification completed in well under a second
  (`ezkl.verify` returned `True`). These are single-run numbers on one
  small model on unspecified-to-you hardware -- treat as illustrative, not
  a benchmark claim, and re-measure on your actual deployment target before
  citing a number anywhere.
- Input commitments (`C_X`) are computed over the plaintext input, bound
  with a 256-bit nonce and the job ID (`protocol/commitments.py`) -- fixed
  from the earlier version, which hashed the *ciphertext*, binding nothing
  to the actual data.
- Model commitments (`C_W`) exist and are checked by the client
  (`client_demo.py`) against what it registered for -- this is what
  detects a node silently substituting a cheaper/different model.
- The commit-then-challenge ordering is enforced in code
  (`prover_node.py`): the node commits `C_Y` to an append-only,
  hash-chained ledger (`protocol/ledger.py`) *before* the challenge
  randomness is read, and the ledger's tamper-evidence is tested directly
  (`test_integration.py` step 5 flips a byte and confirms detection).
- The economic deterrence bound (`protocol/deterrence.py`) is enforced,
  not just asserted: `gateway_server.py` rejects a job if the assigned
  node's posted stake doesn't satisfy `S > gain/audit_probability` for that
  job's value, before any payment is initialized.

## What's still not solved (open problems, unchanged from the concept note unless noted)

- **Randomness beacon**: `challenge.py` implements `DrandBeacon` against
  drand's real public API shape, but this development environment cannot
  reach it (no network path). It has not been exercised against a live
  beacon. `LocalTestBeacon` exists for offline dev only and is refused
  unless `SOVEREIGN_ZK_ALLOW_INSECURE_BEACON=1` is explicitly set, so it
  can't be silently used in a production config.
- **Nitro deployment**: `NitroEnclaveBackend` is written to the correct,
  documented AWS attestation pattern (see its docstring and
  `DEPLOY_NITRO.md`) but has never run against real Nitro hardware -- there
  is none in this environment. It fails closed (raises) rather than
  silently falling back to the simulated path, which is the property that
  matters most for a privacy-critical component, but "fails closed
  correctly" is not the same claim as "has been verified against real
  hardware."
- **Stake custody**: `gateway_server.py`'s `NODE_REGISTRY[...]["staked_ngn"]`
  is a number this gateway trusts itself on. The hash-chained ledger
  protects against a node rewriting history; it does **not** protect
  against a dishonest *operator* of this gateway editing that number. A
  real deployment needs the stake held somewhere the gateway can't
  unilaterally move (an actual escrow account or on-chain bond).
- **Quantization tolerance (ε)**: not yet measured against a production
  model. The calibration run in `model_setup.py` reported a max absolute
  error of ~0.000154 for this specific toy model -- re-run calibration and
  record this number for any model you actually deploy; do not assume it
  transfers.
- **Output / metadata leakage**: `C_Y` and `output` are still visible to
  the client and (via `gateway_server.py`) the gateway operator. Nothing
  here hides job sizes, timing, or payment amounts from someone watching
  the gateway.
- **NDPA "appropriate safeguards" status**: unresolved; needs review by
  Nigerian data-protection counsel. Nothing in this code constitutes legal
  compliance by itself.
- **Side channels / physical attacks**: out of scope for both backends.
  Even a correctly deployed Nitro Enclave does not claim to defend against
  an adversary with physical access to the host (see `DEPLOY_NITRO.md`).

## Threat model (brief)

**In scope:** a remote software adversary (compromised host OS, malicious
co-tenant process) attempting to read plaintext input, or a node operator
attempting to substitute a cheaper/different model or fabricate a result.

**Out of scope:** an adversary with physical hardware access to the host
running the enclave; side-channel attacks against TDX/SEV-SNP/Nitro;
compromise of the hardware vendor's attestation root; compromise of the
gateway operator itself (see "Stake custody" above).

**Trust assumptions:** the hardware vendor and its attestation chain
(NVIDIA/Intel/AMD/AWS) are honest; the drand beacon (once actually wired
up) is live and unbiased; the gateway operator does not collude with a
node to falsify the stake ledger.
