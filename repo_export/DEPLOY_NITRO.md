# Deploying NitroEnclaveBackend on real AWS Nitro Enclaves

`sovereign_zk/enclave/nitro.py` is written against AWS's real attestation
pattern, but it cannot run anywhere other than inside an actual Nitro
Enclave -- there is no way to test or simulate real hardware attestation
in a normal dev container. This is a runbook for an actual deployment, not
something that can be verified from this repository alone.

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

```bash
# Build a container image containing prover_node.py, the sovereign_zk
# package, model artifacts, and AWS's kmstool_enclave_cli binary
# (from aws/aws-nitro-enclaves-sdk-c -- build or vendor it, do not
# reimplement the attestation protocol it performs).
docker build -t sovereign-zk-enclave -f Dockerfile.enclave .

# Convert to an Enclave Image File (.eif)
nitro-cli build-enclave \
  --docker-uri sovereign-zk-enclave \
  --output-file sovereign-zk.eif
# Note the printed PCR0 value -- this is what you put in the KMS key policy.
```

## 3. Configure the vsock proxy on the parent instance

```
# /etc/nitro_enclaves/vsock-proxy.yaml
allowlist:
  - {address: kms.<region>.amazonaws.com, port: 443}
# Nothing else. This is what makes "the enclave cannot exfiltrate data
# anywhere except KMS" actually true.
```

```bash
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
