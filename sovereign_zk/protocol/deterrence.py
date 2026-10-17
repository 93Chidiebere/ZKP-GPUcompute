"""
Economic deterrence bound (concept note Sec. 3).

E[profit from cheating on one inference] = g - q*S
For this to be STRICTLY negative:  S > g / q   (not >=, per round-2 review A6).

This module also makes explicit the assumptions the concept note flags as
open (Sec. 3, items 1-2), because they change the required stake:

  - If a cheating node can get away with k consecutive unchallenged
    inferences before being caught, probability of evading detection on all
    k is (1-q)^k, not just (1-q). required_stake() below lets you size S for
    a target maximum evasion probability over k attempts, not just one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeterrenceResult:
    gain_per_cheat: float
    audit_probability: float
    minimum_stake: float          # strict bound S > g/q, reported as the infimum
    recommended_stake: float      # with a safety margin
    evasion_probability_single: float   # P(no audit) for one cheat
    evasion_probability_k: dict[int, float]  # P(evades all k audits) for sample k's


def required_stake(gain_per_cheat: float, audit_probability: float, safety_margin: float = 1.25) -> DeterrenceResult:
    if audit_probability <= 0 or audit_probability > 1:
        raise ValueError("audit_probability must be in (0, 1]")
    if gain_per_cheat < 0:
        raise ValueError("gain_per_cheat must be >= 0")

    minimum_stake = gain_per_cheat / audit_probability
    recommended_stake = minimum_stake * safety_margin

    evasion_single = 1 - audit_probability
    evasion_k = {k: evasion_single ** k for k in (1, 10, 50, 100, 460)}

    return DeterrenceResult(
        gain_per_cheat=gain_per_cheat,
        audit_probability=audit_probability,
        minimum_stake=minimum_stake,
        recommended_stake=recommended_stake,
        evasion_probability_single=evasion_single,
        evasion_probability_k=evasion_k,
    )


def expected_profit_from_cheating(gain_per_cheat: float, audit_probability: float, stake: float) -> float:
    """g - q*S. Must be < 0 for deterrence to hold; this function lets the
    gateway sanity-check a proposed SLA stake before accepting a node into
    the registry."""
    return gain_per_cheat - audit_probability * stake
