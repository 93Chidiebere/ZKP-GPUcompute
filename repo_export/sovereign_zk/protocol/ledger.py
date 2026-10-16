"""
Append-only, hash-chained settlement ledger.

HONESTY NOTE: the concept note's round-2 draft put settlement on a public
blockchain. That requires blockchain infrastructure this environment has no
path to (and, per the round-2 review, posting Y/C_x on a public chain leaks
information and gas costs were never justified). This module is a
deliberately simpler substitute: a local, tamper-evident, hash-chained log
that plays the SAME ROLE a smart contract would play (an append-only,
independently-checkable record of commitments / challenges / settlements).

It is NOT decentralized. A dishonest operator of this ledger could still
rewrite history (nothing here replaces the need for a trust-minimized
settlement layer in a real multi-operator deployment). What it DOES give
you, which the original prototype had none of:
  - every entry is linked to the previous entry's hash, so any edit to
    earlier history is detectable by recomputing the chain;
  - a single, append-only record of: job commit -> challenge decision ->
    proof result -> payment outcome, so "what happened and in what order"
    is auditable after the fact, which the round-1/round-2 reviews flagged
    as entirely missing.

For a real multi-node, multi-operator deployment, swap this module for an
actual rollup/L2 or a multi-party append-only log (e.g. a Merkle log
replicated across operators) -- the call sites in gateway_server.py don't
need to change, only this file does.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


GENESIS_HASH = "0" * 64


@dataclass
class LedgerEntry:
    seq: int
    ts: float
    kind: str           # "job_commit" | "challenge_decision" | "proof_result" | "settlement"
    payload: dict
    prev_hash: str
    entry_hash: str = field(init=False)

    def __post_init__(self):
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        body = json.dumps(
            {"seq": self.seq, "ts": self.ts, "kind": self.kind, "payload": self.payload, "prev_hash": self.prev_hash},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(body).hexdigest()

    def to_dict(self) -> dict:
        return {
            "seq": self.seq, "ts": self.ts, "kind": self.kind, "payload": self.payload,
            "prev_hash": self.prev_hash, "entry_hash": self.entry_hash,
        }


class Ledger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")

    def _last_hash(self) -> str:
        last = GENESIS_HASH
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)["entry_hash"]
        return last

    def _next_seq(self) -> int:
        n = 0
        with open(self.path, "r") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    def append(self, kind: str, payload: dict) -> LedgerEntry:
        entry = LedgerEntry(
            seq=self._next_seq(), ts=time.time(), kind=kind, payload=payload, prev_hash=self._last_hash(),
        )
        with open(self.path, "a") as f:
            f.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return entry

    def verify_chain(self) -> bool:
        """Recomputes every hash and checks linkage. Returns False the
        instant something doesn't match -- i.e. tamper-evidence."""
        prev = GENESIS_HASH
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d["prev_hash"] != prev:
                    return False
                recomputed = LedgerEntry(
                    seq=d["seq"], ts=d["ts"], kind=d["kind"], payload=d["payload"], prev_hash=d["prev_hash"],
                )
                if recomputed.entry_hash != d["entry_hash"]:
                    return False
                prev = d["entry_hash"]
        return True

    def entries(self) -> list[dict]:
        out = []
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
