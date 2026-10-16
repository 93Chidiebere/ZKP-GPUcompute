"""
Commit-then-challenge sampling (concept note Sec. 2.2 / round-2 review A5).

Security-critical ordering, enforced by the caller (prover_node.py):
  1. Node runs inference, computes C_Y, and PUBLISHES C_Y (ledger.py).
  2. ONLY AFTER that commitment is recorded does the code read the beacon
     round and decide whether this job is challenged.
If the node could choose the challenge outcome (or know it in advance), it
could cheat only on jobs it knows will never be audited -- which is exactly
the attack this ordering prevents.

Two beacon implementations:
  - DrandBeacon: real public randomness beacon (api.drand.sh / League of
    Entropy). This is what a production deployment should use. It cannot be
    reached from this development container (restricted egress), so it is
    written but not exercised by the local test run below.
  - LocalTestBeacon: os.urandom-based stand-in for offline development
    ONLY. It is explicitly insecure for production: whoever controls the
    process calling it also controls the "randomness", so a colluding
    client+node pair could bias challenge selection. main() refuses to use
    it unless SOVEREIGN_ZK_ALLOW_INSECURE_BEACON=1 is set, specifically so
    nobody copy-pastes this into a prod config by accident.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BeaconRound:
    round_number: int
    randomness: bytes  # raw entropy for this round
    source: str        # "drand" | "local-test-INSECURE"


class RandomnessBeacon(ABC):
    @abstractmethod
    def latest_round(self) -> BeaconRound: ...


class DrandBeacon(RandomnessBeacon):
    """Public randomness beacon client (https://drand.love).

    NOTE: not reachable from this sandbox's egress allowlist. The HTTP call
    is written against drand's documented public API shape so it can be
    dropped into a normal-network deployment unchanged; it is not something
    this environment can execute or verify.
    """

    def __init__(self, base_url: str = "https://api.drand.sh"):
        self.base_url = base_url.rstrip("/")

    def latest_round(self) -> BeaconRound:
        import requests  # local import: only needed on this path
        resp = requests.get(f"{self.base_url}/public/latest", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return BeaconRound(
            round_number=data["round"],
            randomness=bytes.fromhex(data["randomness"]),
            source="drand",
        )


class LocalTestBeacon(RandomnessBeacon):
    """INSECURE stand-in for local development / CI only."""

    def __init__(self):
        self._round = 0

    def latest_round(self) -> BeaconRound:
        self._round += 1
        return BeaconRound(
            round_number=self._round,
            randomness=os.urandom(32),
            source="local-test-INSECURE",
        )


def get_beacon() -> RandomnessBeacon:
    if os.environ.get("SOVEREIGN_ZK_ALLOW_INSECURE_BEACON") == "1":
        return LocalTestBeacon()
    return DrandBeacon()


def should_challenge(
    beacon_round: BeaconRound,
    job_id: str,
    c_x: str,
    c_w: str,
    c_y: str,
    audit_probability: float = 0.01,
) -> bool:
    """Deterministic given (beacon round, job commitments) -- anyone can
    recompute this and verify the challenge decision after the fact, which
    is what makes the sampling publicly auditable rather than something the
    node could claim selectively.

    val = first 8 bytes of SHA256(round_randomness || job_id || C_X || C_W || C_Y)
          interpreted as a uniform fraction in [0, 1)
    challenged iff val < audit_probability
    """
    h = hashlib.sha256()
    h.update(beacon_round.randomness)
    h.update(job_id.encode("utf-8"))
    h.update(c_x.encode("utf-8"))
    h.update(c_w.encode("utf-8"))
    h.update(c_y.encode("utf-8"))
    digest = h.digest()
    val = int.from_bytes(digest[:8], "big") / 2**64
    return val < audit_probability
