"""
DEPRECATED. Use prover_node.py instead.

This file is kept only so old imports don't hard-crash. It had two
concrete problems fixed in prover_node.py:
  1. Decrypted plaintext was written to a persistent-disk path
     ("temp_enclave_input.json") and only deleted via os.remove() AFTER
     ezkl.prove() returned -- an exception mid-pipeline left it behind.
     prover_node.py's SimulatedEnclaveBackend uses a tmpfs-backed
     (/dev/shm) directory with cleanup in a `finally` block instead.
  2. Every job was proven (no sampling), which is the "economically
     unviable" path the concept note explicitly argues against.
     prover_node.py implements commit-then-challenge sampling.

It also called ezkl.prove(witness, model, pk, proof_path, "single", srs) --
that 6-argument form does not match ezkl>=23's signature
(prove(witness, model, pk_path, proof_path, srs_path)), so this file would
fail outright against the pinned requirements.txt even unmodified.
"""
raise ImportError(
    "kenya_enclave_server.py is deprecated and known-broken against the "
    "pinned ezkl version. Use `python3 prover_node.py` instead."
)
