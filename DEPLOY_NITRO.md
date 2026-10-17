# Deploying NitroEnclaveBackend on real AWS Nitro Enclaves

`sovereign_zk/enclave/nitro.py` is written against AWS's real attestation
pattern, but it cannot run anywhere other than inside an actual Nitro
Enclave -- there is no way to test or simulate real hardware attestation
in a normal dev container. This is a runbook for an actual deployment, not
something that can be verified from this repository alone.

## 0. Do you need GPU confidential computing yet?

Probably not for a first deployment. The model `model_setup.py` currently
trains and compiles (5→16→1 MLP) is small enough to run comfortably on a
CPU-only TEE (Nitro Enclave, no GPU involved). NVIDIA H100 confidential-
computing mode is a separate, much more involved, and more expensive path
(specific instance types, specific driver/firmware versions, limited
availability) that only matters once you're actually serving a model large
enough to need GPU compute in the first place. Recommended order:

1. Get `NitroEnclaveBackend` working CPU-only (steps below) against the
   current toy model. This validates the attestation/KMS/vsock plumbing,
   which is identical whether or not a GPU is involved.
2. Only once that's working, separately evaluate whether your actual
   target model needs CC-GPU hardware at all, and treat that as its own
   deployment effort with its own runbook -- it is not a small addition to
   this one.

## 1. Prerequisites

- An EC2 instance type that supports Nitro Enclaves (e.g. `m5.xlarge` or
  larger), with Nitro Enclaves enabled on launch
  (`--enclave-options 'Enabled=true'`).
- `nitro-cli` and `nitro-enclaves-sdk` installed on the **parent** instance
  (not the enclave).
- An AWS KMS key whose **key policy** includes a condition requiring a
  valid Nitro attestation document with specific PCR0 (enclave image hash)
  values. This is the actual root of the privacy guarantee -- see AWS's
  "Cryptographic attestation" documentation for the exact policy JSON
  shape (`kms:RecipientAttestation:ImageSha384`, etc).
- A CC-capable GPU setup (NVIDIA H100 confidential-computing mode) if GPU
  inference inside the enclave is required; CPU-only TDX/SEV-SNP is
  sufficient for CPU-bound models.

## 2. Build the enclave image

`Dockerfile.enclave` (repo root) builds a container with `prover_node.py`,
the `sovereign_zk` package, your model artifacts, and AWS's own
`kmstool_enclave_cli` (vendored from `aws/aws-nitro-enclaves-sdk-c`, not
reimplemented -- see that file's comments). Run `model_setup.py` first so
`network.compiled` / `vk.key` / `pk.key` / `kzg.srs` / `settings.json`
exist to be copied in.

```bash
python3 model_setup.py   # produces the artifacts Dockerfile.enclave copies in
docker build -t sovereign-zk-enclave -f Dockerfile.enclave .

# Convert to an Enclave Image File (.eif)
nitro-cli build-enclave \
  --docker-uri sovereign-zk-enclave \
  --output-file sovereign-zk.eif
# Note the printed PCR0 value -- this is what you put in the KMS key policy.
```

## 3. Configure the vsock proxy on the parent instance

`vsock-proxy.yaml` (repo root) is the allowlist config -- edit `<region>`,
copy it to `/etc/nitro_enclaves/vsock-proxy.yaml` on the parent instance,
and start the proxy:

```bash
cp vsock-proxy.yaml /etc/nitro_enclaves/vsock-proxy.yaml
vsock-proxy 8000 kms.<region>.amazonaws.com 443 \
  --config /etc/nitro_enclaves/vsock-proxy.yaml &
```

## 4. Run the enclave

```bash
nitro-cli run-enclave \
  --eif-path sovereign-zk.eif \
  --cpu-count 4 \
  --memory 4096 \
  --enclave-cid 16
```

Credentials (an IAM role/session scoped to *only* `kms:Decrypt` on the
specific key) must be forwarded to the enclave over vsock at launch --
`sovereign_zk/enclave/nitro.py` does not provision credentials itself; see
AWS's enclave credential-forwarding samples for the standard pattern.

## 5. Point prover_node.py at the real backend

In `prover_node.py`, replace:

```python
BACKEND = SimulatedEnclaveBackend()
```

with:

```python
from sovereign_zk.enclave.nitro import NitroEnclaveBackend
BACKEND = NitroEnclaveBackend(kms_key_id="<key-id>", region="<region>")
```

This must run **inside** the enclave image built in step 2. Running it on
the parent instance (or anywhere without `/dev/nsm`) will raise
`NotRunningInEnclaveError` by design -- it fails closed rather than
silently using an unisolated path.

## 6. Verify before trusting

Hit `/attest` on the running node. For a correctly deployed enclave it
should report:

```json
{"backend_kind": "aws-nitro-enclave", "isolated_from_host": true, ...}
```

If it reports `"backend_kind": "simulated"`, the deployment did not
actually switch backends -- do not treat that node as privacy-preserving
regardless of what its hostname or marketing says. This is exactly the
check `client_demo.py` performs automatically before submitting any job.
