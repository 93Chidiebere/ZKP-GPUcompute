# Related work: comparison

Prose citations ("X is similar to Slalom") don't tell a reviewer *where*
a system sits relative to prior work on the dimensions that actually
matter for this problem. This table makes the comparison explicit, on
axes chosen because they're exactly where this project's own design
decisions were contested across its review rounds: hardware trust,
whether the proof is exhaustive or sampled, whether cheating is only
*detected* or also *deterred economically*, and what's actually been run
versus designed.

| System | Confidentiality mechanism | Integrity mechanism | Proves every inference? | Economic deterrence enforced? | Settlement conditioned on outcome? | What's actually been executed |
|---|---|---|---|---|---|---|
| **Slalom** (Tramèr & Boneh, 2019) | Small trusted enclave (SGX) for blinding; bulk compute on untrusted GPU | Freivalds-style randomized linear-algebra check (not a full ZK proof) | No -- per-layer statistical check | No (no economic/payment layer; academic prototype) | N/A | Full implementation + benchmarks (published) |
| **Delphi** (Mishra et al., 2020) | Pure cryptography (secret sharing / garbled circuits), no hardware trust | Cryptographic protocol correctness, not an auditable proof artifact | Every inference, by construction | No | N/A | Full implementation + benchmarks (published) |
| **Generic "prove every inference" ZKML** (as surveyed in Peng et al., 2025) | None by itself -- usually paired with a separate confidentiality mechanism, or assumes public input | Full zk-SNARK per inference | Yes | No | No | Varies by cited system; the survey's own point is that per-inference cost is the field's central bottleneck |
| **VeriML / zkMLaaS-style sampling** (Zhao et al., 2021; Huang et al., 2022) | Not their focus -- oriented at verifiable *training*, not confidential *inference* | Commitment + verifier-selected sampling, similar sampling principle to this work | No -- sampled | Fairness/payment mechanisms discussed but not an explicit `S > g/q` bound with a code-enforced check | Partially (payment fairness is a stated goal) | Published results on training verification, not inference |
| **Sovereign-ZK (this work)** | Confidential computing (TEE) for every inference | zk-SNARK (EZKL/halo2) for a *sampled* subset, commit-then-challenge ordered | No -- sampled, ~1% by default | **Yes** -- `S > g/q` stated as a proposition (Section 6, `FORMAL_SECURITY.md`) and enforced as a pre-routing check in `gateway_server.py`, tested directly | **Yes** -- `gateway_server.py` pays/refunds/slashes based on challenge outcome, tested directly | Confidential-computing backend: **not yet run on real TEE hardware**. Sampled-audit pipeline, settlement logic, and deterrence check: run end to end, with real EZKL proving/verification and measured timings (`SECURITY.md`) |

## What this table is for, honestly

The last column is the one worth reading carefully before citing this
project as more mature than it is. Slalom and Delphi are *published,
benchmarked systems*. This work's novelty is the specific combination
(confidential computing for every inference + sampled ZK audit + an
economic deterrence bound that is checked in code, not just stated) and
the fact that the sampling/settlement/deterrence layer has been
implemented and tested -- but the confidentiality layer that makes the
whole thing trustworthy for real sensitive data has not been validated
on real hardware (`SECURITY.md`, `DEPLOY_NITRO.md`). A fair framing for
a paper: **the contribution is a tested protocol design and reference
implementation for the audit/settlement layer, with the hardware-trust
layer specified but not yet empirically validated** -- not "a complete,
production-validated system."

## Gaps this comparison exposes in the current work

1. No side-by-side *performance* comparison against Slalom or Delphi on
   the same task -- their published benchmarks use different models and
   hardware, so a credible comparison requires re-running at least one
   of them (or a close reimplementation) under the same conditions this
   project measures itself under. This is real future work, not
   something to claim without doing it.
2. VeriML/zkMLaaS are the closest prior art on the *sampling* idea
   specifically. A careful related-work section should engage with
   whether their fairness/payment mechanisms already solve what Section
   6 of `FORMAL_SECURITY.md` calls open (repeated-play exposure, stake
   custody) rather than assuming they don't -- this table was built from
   the survey's characterization of them, not a close reading of either
   paper, and that close reading is worth doing before the related-work
   section is finalized.
