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
- **Corrected benchmark (see "Benchmark correction" below): proving a
  5→16→1 MLP takes ~8 seconds; verification takes ~0.03 seconds.**
  Measured through the actual production pipeline (`test_integration.py`),
  not an isolated script. These are single-run numbers on one small model
  on unspecified-to-you hardware -- treat as illustrative, not a benchmark
  claim, and re-measure on your actual deployment target before citing a
  number anywhere.

### Benchmark correction (superseded numbers)

An earlier version of this file reported **74.4s proving / "well under a
second" verification**. Both model_setup.py and the scaling benchmark that
produced that number shared a bug: the KZG SRS (trusted setup) degree was
hardcoded to 17 regardless of what the circuit actually needed, rather
than using the degree EZKL's own calibration step (`logrows` in
`settings.json`) determined was sufficient -- 15, for this model. An
oversized SRS doesn't just waste disk space; every prove/verify call pays
proportional cost to generate and check openings against it. Measured
side by side on the identical model and identical input:

| | SRS degree 17 (bug) | SRS degree 15 (calibrated, fixed) |
|---|---|---|
| Prove time | 76.17s | 8.23s (9.3x faster) |
| Verify time | 67.52s | 0.030s (2,270x faster) |
| Proving key size | 138,479,371 bytes | 138,479,371 bytes (unexplained -- see below) |

The fix (`model_setup.py`, `benchmark_fix_check.py`) is to read
`settings.json`'s calibrated `logrows` and pass that to `ezkl.gen_srs()`
directly, instead of a hardcoded constant. This also resolved an
apparent contradiction flagged in earlier review rounds of this project
(round 2: "Section 2.1 says SNARK proofs verify in milliseconds... yet
verification took 26.44s") -- that contradiction was real, and was never
actually about the SNARK scheme's properties; it was this SRS-sizing bug,
present since the project's first prototype.

A separate bug was found in the same benchmarking pass: the five-model
scaling sweep (`benchmark_scaling.py`) trained each model against
mismatched data -- `train_mlp(X, make_data()[1], hidden)` generated a
*second*, unrelated random dataset just to extract its labels, training
every model against inputs and labels that didn't correspond to each
other. Reported train accuracy for all five configurations was ~51-56%
(chance level) as a direct result; the corrected run (consistent X, y)
reached 93.25%, matching `model_setup.py`'s original figure. **Any
"trained model" claim from a script other than `model_setup.py` itself
should be treated as unverified until re-run with this fix.**

One result from that corrected run is still unexplained and reported
rather than hidden: proving-key size was byte-identical (138,479,371
bytes) whether the SRS was generated at degree 17 or degree 15, even
though prove/verify time dropped sharply. Either `pk.key` size in this
EZKL version is not primarily determined by SRS degree for circuits this
small, or there is caching behavior (e.g. a `$HOME`-keyed SRS/key cache)
this investigation did not isolate. Flagged as an open question rather
than asserted either way -- do not cite the pk-size figure as evidence of
anything until this is resolved.

**What this means for anything already cited from this project**: the
BUILD 2026 abstract and any prior conversation referencing "74.4s /
67.2s" or "sub-second verification" as an assumption rather than a
measurement should be corrected to the numbers in this section.
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
