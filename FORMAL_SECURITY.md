# Formal security argument

This document states the commit-then-challenge protocol's security
properties as explicit claims with explicit assumptions, rather than as
prose. It is written to be dropped into a paper's "Security Analysis"
section. Where a claim is only partially established by the current
implementation, that gap is stated, not hidden -- consistent with the
rest of this repository's documentation.

## 1. Setup

Let `H` be SHA-256, modeled as a random oracle for this analysis. Let
`Sign_node` denote the node's capability to append entries to its ledger
(`protocol/ledger.py`); let `Beacon` be a randomness source producing
`r_i` for round `i`, unpredictable before round `i` is published and
unbiasable by any single party (Section 5 discusses how far this holds
for the two beacon implementations actually in the codebase).

For a job with identifier `job_id`, plaintext input `X`, model `W`
(represented by its compiled circuit and verification key):

```
nonce          <-$ {0,1}^256                         (client, secret until reveal)
C_X  = H(X || nonce || job_id)                        (commitments.py: commit_input)
C_W  = H(compiled_circuit || vk)                       (commitments.py: commit_model)
Y, witness     = Infer(X, W)                           (inside EnclaveBackend)
salt_Y <-$ {0,1}^256
C_Y  = H(Y || job_id || salt_Y)                        (commitments.py: commit_output)
```

The node appends `(job_id, C_X, C_W, C_Y)` to its ledger (a `job_commit`
entry) BEFORE reading `Beacon`'s current round. Only after that append is
`r_i` read and

```
challenged = ( first 8 bytes of H(r_i || job_id || C_X || C_W || C_Y) ) / 2^64  <  q
```

is computed (`protocol/challenge.py: should_challenge`), where `q` is the
public audit probability.

## 2. Claim 1 -- Input binding

**Claim.** A computationally bounded node cannot produce a valid-looking
response for `job_id` that is consistent with a plaintext input `X' != X`
that the client actually submitted, except with probability negligible in
the nonce length (256 bits), assuming `H` behaves as a random oracle and
the client's `nonce` remains secret until any reveal phase.

**Argument.** `C_X` is published by the client before the job executes
and is bound to `X` via `H(X || nonce || job_id)`. Finding `X' != X` with
`H(X' || nonce || job_id) = C_X` without knowledge of `nonce` requires
either a second preimage of `H` (negligible under the random-oracle
assumption) or guessing `nonce` directly (probability `2^-256`). This
holds regardless of what the node does during inference -- the commitment
is computed and published by the client, not the node, so the node has no
opportunity to bias it.

**Gap from the pre-formalization version.** An earlier prototype of this
system (documented in this repository's history) computed `C_X` over the
*ciphertext* the client transmitted, not over `X` itself. That version's
"input binding" bound nothing to the plaintext data at all -- a node
could decrypt, substitute any `X'`, and the published commitment would
still verify, because the commitment never referenced `X` in the first
place. This claim only holds for the current `commitments.py`
implementation; it is stated explicitly because getting this wrong is a
realistic failure mode, not a hypothetical one.

## 3. Claim 2 -- Model binding

**Claim.** If a client checks a node's claimed `C_W` against a
previously registered commitment for the model it intends to use, and
rejects on mismatch (as `client_demo.py` does), then a node cannot
substitute a different compiled circuit or verification key without
detection, under the same random-oracle assumption on `H`.

**Argument.** Direct from collision resistance of `H`: two distinct
`(compiled_circuit, vk)` pairs producing the same `C_W` requires a
collision, negligible for SHA-256.

**Gap.** This claim protects against *detectable* substitution -- the
client learns a mismatch occurred. It does not by itself force a node to
*use* the registered model; a node that reports the correct `C_W` while
actually executing a different model during inference would need the
Claim 3 integrity check (the ZK proof, when challenged) to be caught.
Claim 2 alone only covers the unaudited (unchallenged) path's weakest
link: a node cannot even *claim* to be running a model it never
registered.

## 4. Claim 3 -- Challenge unpredictability

**Claim.** A node cannot choose, prior to its `C_Y` commitment being
recorded, which of its jobs will be challenged, assuming `Beacon`'s round
`r_i` is unknown to the node at commitment time and `H` is a random
oracle.

**Argument.** `should_challenge` is a deterministic function of `(r_i,
job_id, C_X, C_W, C_Y)`. The node commits `C_Y` to the ledger (an
append-only structure whose tamper-evidence is established by Claim 4)
strictly before `r_i` for the relevant round is available. At commitment
time, the node's view of `should_challenge`'s eventual output is
therefore no better than guessing, assuming `r_i` is unpredictable before
publication -- which is a property of the randomness source, not of this
protocol, and is exactly where Section 5's caveats about `DrandBeacon`
vs. `LocalTestBeacon` matter.

**Gap -- the one this analysis considers most important to flag.** This
claim's soundness is entirely inherited from the beacon. The current
codebase has NOT exercised `DrandBeacon` against drand's live network
from any environment (confirmed: no network path from the development
sandbox used to build this repository). A node operator who also
controlled the "randomness" source -- which is exactly what
`LocalTestBeacon` is, and exactly why it requires an explicit opt-in
environment variable to use -- could predict or bias `r_i` and defeat
this claim entirely. **Claim 3 is a conditional claim, not yet an
end-to-end verified one; closing this gap requires live network
verification, not further code changes.**

## 5. Claim 4 -- Ledger tamper-evidence

**Claim.** Given a hash-chained ledger (`protocol/ledger.py`) where entry
`i`'s hash includes entry `i-1`'s hash, any single-entry modification
after the fact is detectable by recomputing the chain, with the same
collision-resistance assumption on `H`.

**Argument.** Standard hash-chain argument; modifying entry `i` changes
`entry_hash_i`, which no longer matches what entry `i+1` recorded as
`prev_hash`, breaking the chain at `i+1` under `verify_chain()`.

**Empirically tested, not just argued**: `test_integration.py` step 5
flips a single byte in a stored `C_Y` value and confirms `verify_chain()`
returns `False`. This is one of the few claims in this document with
direct test coverage beyond the cryptographic argument.

**Gap.** This protects against a dishonest *node* rewriting its own
history. It does NOT protect against a dishonest *operator of the
ledger's storage* (in the current single-gateway deployment, the gateway
operator) simply replacing the entire ledger file wholesale with a
different internally-consistent chain. Detecting that requires an
external, independent witness to the chain's head hash over time (a
public anchor), which is explicitly listed as unimplemented in
`SECURITY.md`'s "Stake custody" section.

## 6. Proposition -- Economic deterrence bound

**Proposition.** Let `g` be a node's expected gain from successfully
cheating on one inference (serving an incorrect or substituted result
without detection), and let `q` be the audit probability. If the node has
posted a stake `S` that is forfeited on a failed challenge, then cheating
has strictly negative expected value if and only if `S > g / q`.

**Proof.** Expected profit from cheating on one inference is `g - q*S`
(gain if unaudited, which happens with probability `1-q` and contributes
`g`; loss of `S` if audited, which happens with probability `q`,
contributing `-q*S`; summing: `(1-q)*g + q*(g - S) = g - q*S`). This is
strictly negative iff `S > g/q`. QED.

**This is enforced in code, not only stated**: `gateway_server.py`
computes `required_stake(gain_per_cheat, audit_probability)` and refuses
to route a job to a node whose posted stake is below this bound before
any payment is initialized (tested directly: a 5,000 NGN job against a 0
NGN stake is rejected with HTTP 409 before any Paystack call is made).

**Gaps, stated precisely rather than left as a single vague caveat:**

1. **Repeated play.** The proposition is a single-shot argument. A node
   that cheats on `k` jobs evades detection on all of them with
   probability `(1-q)^k`, not `(1-q)`. For `q=0.01`, this is ~90% for
   `k=10` and drops below 1% only at `k >= 460`. The *per-incident* bound
   `S > g/q` still makes any single successful audit unprofitable in
   expectation across the node's whole job stream, but it does not bound
   the node's total exposure across many simultaneous or rapid cheats
   before the operator notices a pattern and intervenes. A tighter
   multi-shot bound is open future work.
2. **Stake custody.** The proposition assumes `S` is actually
   forfeit-able -- i.e., held somewhere the node cannot withdraw
   unilaterally and the gateway operator cannot restore unilaterally.
   The current implementation tracks `S` as a number the gateway trusts
   itself on (`SECURITY.md`, "Stake custody"). The proposition's
   soundness is conditional on a custody mechanism this repository does
   not yet implement.
3. **Detection reliability.** The proposition assumes a cheat, if
   audited, is caught with certainty. In practice this depends on the
   circuit's quantization tolerance (`SECURITY.md`'s ε discussion): a
   node whose deviation from the correct output stays within the
   circuit's own floating-point-vs-fixed-point error band may produce a
   verifying proof despite having served a numerically different result
   than intended. This is not a flaw in the ZK proof itself (the proof
   correctly attests that the *quantized circuit* was executed
   correctly) but a gap between what's proven and what the client
   actually wanted -- a point the round-2 review of this project raised
   and which remains open.

## 7. Summary table

| Claim | Status | What would close the gap |
|---|---|---|
| 1. Input binding | Proven, implemented, assumption-complete | -- |
| 2. Model binding | Proven, implemented, assumption-complete | -- |
| 3. Challenge unpredictability | Proven *conditional on beacon honesty*; beacon unverified live | Run `drand_smoketest.py` against the live network; monitor for beacon liveness in production |
| 4. Ledger tamper-evidence | Proven and empirically tested, protects against node, not operator | External public anchoring of the ledger head |
| 5. Deterrence bound | Proven, enforced in code, single-shot only | Multi-shot bound; real stake custody; quantify ε's effect on detection reliability |
