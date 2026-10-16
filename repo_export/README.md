# Sovereign-ZK

A prototype implementation of a **commit-then-challenge** protocol for
cross-border AI inference: a client sends encrypted data to a remote node,
the node runs inference and commits to the result, and a sampled subset of
jobs are backed by a real zero-knowledge proof of correct execution
(EZKL/halo2) rather than every job, which would be too slow for production
use. Companion implementation to the *Sovereign-ZK* concept note.
Developed by **Chidiebere V. Christopher**.

> **Status: prototype.** Read [`SECURITY.md`](SECURITY.md) before using
> this with real sensitive data. The headline claim worth being explicit
> about up front: **the default backend provides no hardware isolation.**
> It runs in an ordinary process and honestly reports that at `/attest`.
> Real confidentiality requires deploying `NitroEnclaveBackend` on actual
> Nitro Enclave hardware -- see [`DEPLOY_NITRO.md`](DEPLOY_NITRO.md).

## What's actually implemented and tested here

- Real EZKL circuit compilation, witness generation, proving and
  verification against a trained (non-trivial-weight) model --
  `model_setup.py` trains a small MLP with plain NumPy gradient descent,
  no placeholder zero weights.
- Input commitments bound to the **plaintext** (not ciphertext), a
  256-bit nonce, and the job ID -- `sovereign_zk/protocol/commitments.py`.
- Model commitments (`C_W`), checked client-side against what the client
  registered for, to catch a node substituting a different model.
- Commit-then-challenge sampling: the node publishes its output
  commitment to a tamper-evident, hash-chained ledger **before** reading
  challenge randomness, so it can't selectively cheat on jobs it predicts
  won't be audited -- `sovereign_zk/protocol/challenge.py` +
  `sovereign_zk/protocol/ledger.py`.
- An economic deterrence check (`S > gain/audit_probability`) actually
  enforced by the gateway before it will route a job to a node --
  `sovereign_zk/protocol/deterrence.py` + `gateway_server.py`.
- Escrow conditioned on outcome: `gateway_server.py` pays a node only
  after a challenged proof verifies (or on stake-backed trust for
  unchallenged jobs), and refunds + slashes on a failed challenge --
  not the pay-before-compute flow of earlier prototype versions.
- `test_integration.py` exercises the whole flow in-process: a forced
  challenge (proving + verification), a forced skip, ledger-chain
  verification, and tamper detection on a corrupted ledger entry. Run it
  yourself: `python3 model_setup.py && python3 test_integration.py`.

See [`SECURITY.md`](SECURITY.md) for the full status matrix, including
what's still an open problem (randomness beacon not exercised against a
live network, Nitro backend not run against real hardware, stake custody,
quantization tolerance, NDPA legal review).

## Installation

```bash
pip install -r requirements.txt
```

(The published PyPI package `sovereign-zk` is an older snapshot;
installing from this repository checkout gets you the current protocol
implementation. `sovereign_zk/client.py` and `sovereign_zk/node.py` are
kept as deprecated compatibility shims that point to the real
implementations below.)

## Quick start (local, simulated backend)

```bash
# 1. Train the model, compile the ZK circuit, publish C_W
python3 model_setup.py

# 2. Start the prover node (simulated backend -- see the WARNING it prints)
python3 prover_node.py &

# 3. Run a client job end to end
python3 client_demo.py

# Or: run the full automated test (forced challenge + forced skip + ledger checks)
python3 test_integration.py
```

`client_demo.py` checks the node's `/attest` response and its model
commitment before submitting anything, and prints plainly whether a given
job's result was cryptographically verified or accepted on economic trust:

```
[*] Node backend: simulated  isolated_from_host=False
[!] This node provides NO hardware isolation. Do not send real sensitive data to it.
...
[*] Job was CHALLENGED -- a full ZK proof was generated. Verifying...
[SUCCESS] Proof verified cryptographically (74.44s to generate).
```

## Architecture

```
client_demo.py  --(encrypted payload, C_X, job_id)-->  prover_node.py
                                                           |
                                               EnclaveBackend.run_confidential_inference()
                                               (SimulatedEnclaveBackend, or
                                                NitroEnclaveBackend on real hardware)
                                                           |
                                               commit C_Y --> ledger.py (hash-chained)
                                                           |
                                               read beacon --> should_challenge()
                                                           |
                                       challenged? --yes--> ezkl.prove() --> proof
                                                 \--no---> output only (stake-backed)
                                                           |
gateway_server.py  <--(result + proof?)--------------------
  | checks node stake against deterrence.required_stake()
  | verifies proof independently if challenged
  | pays node (Paystack Transfer) or refunds + slashes
```

`gateway_server.py`'s settlement ledger is a local hash-chained log
(`protocol/ledger.py`), not a blockchain -- see that module's docstring
for why, and what a production multi-operator deployment would need
instead.

## Deploying with real hardware isolation

See [`DEPLOY_NITRO.md`](DEPLOY_NITRO.md) for the AWS Nitro Enclaves
deployment runbook. `NitroEnclaveBackend` fails closed (raises
`NotRunningInEnclaveError`) rather than silently falling back to the
simulated path if `/dev/nsm` is absent.

## Legal status

Nothing in this repository constitutes legal advice or a compliance
guarantee. Whether this architecture satisfies the Nigeria Data Protection
Act's "appropriate safeguards" requirement is an open question requiring
review by Nigerian data-protection counsel -- see the concept note's
"Open Problems" section.

## 👤 Author

**Chidiebere V. Christopher**
* **LinkedIn**: [Chidiebere Christopher](https://www.linkedin.com/in/chidiebere-christopher/)
* **GitHub**: [93Chidiebere](https://github.com/93Chidiebere)
* **Email**: vchidiebere.vc@gmail.com
