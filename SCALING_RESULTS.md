# Scaling results

`benchmark_scaling.py`'s first run (documented as a methodology failure in
`SECURITY.md`) found no scaling signal because an SRS-sizing bug forced
every config to the same cost floor. `benchmark_scaling_v2.py` fixes both
bugs found there (see that file's docstring) and widens the sweep far
enough to actually find where cost starts growing. Five single-hidden-
layer MLPs (same architecture family as `model_setup.py`), hidden width
16 to 4096, 5 input features, trained on the same consistent synthetic
dataset.

## Results

| config | params | logrows | prove (s) | verify (s) | proof (KB) | pk (MB) | train acc |
|---|---:|---:|---:|---:|---:|---:|---:|
| w16 | 113 | 15 | 9.02 | 0.029 | 16.9 | 132.06 | 0.930 |
| w64 | 449 | 15 | 9.24 | 0.031 | 17.0 | 132.06 | 0.929 |
| w256 | 1,793 | 15 | 8.53 | 0.030 | 17.0 | 132.06 | 0.933 |
| w1024 | 7,169 | **16** | 19.84 | 0.076 | 17.0 | 264.13 | 0.929 |
| w4096 | 28,673 | **18** | 70.78 | 0.294 | 17.0 | 1,056.50 | 0.909 |

## Findings

**1. Cost is a step function of `logrows`, not a smooth function of
parameter count.** From 113 to 1,793 params (15.9x), `logrows` stays at
15 and prove/verify/pk size are flat (within run-to-run noise). The first
jump (15→16, at 7,169 params) costs 2.3x prove time and exactly 2.0x pk
size. The second jump (16→18, at 28,673 params, skipping 17 entirely)
costs another 3.6x prove time and exactly 4.0x pk size (`2^(18-16)`).
**Practical implication for deployment planning**: the question that
matters for cost is not "how big is my model" but "which side of a
`logrows` threshold does my model's calibrated requirement land on" --
two models could differ 16x in parameter count and cost the same, or
differ 4x and cost 2x more, depending entirely on where they fall.

**2. Proof size is constant (~17KB) across a 250x parameter range.** This
is the SNARK succinctness property, and it's worth stating as an
empirical result rather than just a textbook property: whatever the
verifier receives over the network does not grow with model size in this
range, even though the proving key (which stays with the prover) grows
by 8x. This is directly relevant to the "output/metadata leakage" and
bandwidth-cost questions in `SECURITY.md` and `DEPLOY_NITRO.md` -- proof
transmission cost is not a scaling concern here; proving-time compute
cost is.

**3. This re-opens (does not resolve) the pk-size anomaly flagged in
`SECURITY.md`.** That note observed pk size identical (138,479,371 bytes)
whether the SRS was generated at degree 17 (the original bug) or degree
15 (the fix), which was flagged as unexplained. This sweep now shows a
clean, exact 2x and 4x power-of-two relationship between logrows and pk
size, run entirely within one script execution, same process, same
machine. That makes the degree-17-vs-15 comparison in
`benchmark_fix_check.py` MORE suspicious, not less: the "buggy" figure
quoted there was copied from the original (separate, earlier) sweep's
logged output, not re-measured side by side in the same run as the
"fixed" figure. The likely explanation is a stale file, a different
working directory, or an EZKL-side cache keyed by something other than
the SRS path used in that specific comparison -- but this is a guess,
not a finding, and is flagged as exactly that. **The scaling relationship
in this document (2x and 4x, measured cleanly across 5 configs in one
run) should be trusted over the single degree-17-vs-15 comparison in
`benchmark_fix_check.py`, which should be treated as unreliable until
re-run properly isolated.**

## What this does NOT establish

- Only one architecture family (single hidden layer, ReLU, 5 input
  features) was tested. Depth, convolutional layers, and larger input
  dimensions are separate scaling axes, untested here.
- Only CPU proving on one (unspecified-to-you) development machine was
  measured. Absolute numbers will differ on deployment hardware; the
  *relative* step-function behavior at logrows boundaries should
  transfer, but hasn't been verified to.
- The exact parameter count at which each `logrows` boundary falls
  depends on the model's weight distribution and EZKL's calibration
  (`input_scale`/`param_scale` search), not only parameter count -- two
  models with the same parameter count but different weight magnitudes
  could calibrate to different `logrows`. Treat the specific thresholds
  found here (between 1,793 and 7,169 params; between 7,169 and 28,673)
  as illustrative of this model family, not a general formula.
