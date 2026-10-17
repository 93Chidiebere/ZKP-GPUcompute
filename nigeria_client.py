"""
DEPRECATED. Use client_demo.py instead.

This file computed C_X over the ENCRYPTED payload (encrypted_data_path +
nonce + job_id), not the plaintext input -- that binds the commitment to
nothing about the actual data (see sovereign_zk/protocol/commitments.py's
docstring). client_demo.py fixes this and adds ledger verification, model
commitment checking, and the commit-then-challenge flow.
"""
raise ImportError(
    "nigeria_client.py is deprecated. Use `python3 client_demo.py` instead."
)
