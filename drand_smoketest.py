"""
Run this from a machine with normal internet access (NOT this sandbox --
confirmed no path to api.drand.sh from there). Confirms the real beacon
response matches what challenge.py's DrandBeacon expects, and that two
consecutive rounds actually differ (sanity check against a misconfigured
mock).

    python3 drand_smoketest.py
"""
import sys
sys.path.insert(0, ".")  # run from repo root

from sovereign_zk.protocol.challenge import DrandBeacon

# quicknet: fast (~3s) rounds, unchained -- good fit for per-job challenge
# decisions where you don't want jobs waiting on a ~30s legacy round.
# Pin the chain hash explicitly rather than relying on "default network".
QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"

beacon = DrandBeacon(base_url=f"https://api.drand.sh/{QUICKNET_CHAIN_HASH}")

r1 = beacon.latest_round()
print(f"round={r1.round_number} randomness={r1.randomness.hex()[:16]}... source={r1.source}")
assert r1.source == "drand"
assert len(r1.randomness) == 32, f"expected 32 bytes, got {len(r1.randomness)}"

import time
time.sleep(4)
r2 = beacon.latest_round()
print(f"round={r2.round_number} randomness={r2.randomness.hex()[:16]}...")
assert r2.round_number > r1.round_number, "round did not advance -- check chain hash / network"
assert r2.randomness != r1.randomness

print("OK: DrandBeacon matches the real API and rounds advance as expected.")
