"""Paired firm-level resampling (Technical Appendix D.5, Inference).

Uncertainty for every statistic, including macro-F1 and arm differences, is estimated by
resampling firms with replacement, keeping every passage, edit pair, arm and repeated run
of a sampled firm together, so firm-level dependence and the paired design are preserved.
"""
from __future__ import annotations

import random
from typing import Callable, Mapping, Sequence


def firm_bootstrap(stat: Callable[[list], float], groups: Mapping[str, Sequence], n_boot: int = 2000,
                   seed: int = 0, level: float = 0.95) -> dict:
    """``stat`` receives a flat list of units; ``groups`` maps firm -> its units (all arms together)."""
    rng = random.Random(seed)
    firms = list(groups)
    point = stat([u for f in firms for u in groups[f]])
    draws = []
    for _ in range(n_boot):
        sample = []
        for _ in firms:
            sample.extend(groups[rng.choice(firms)])
        draws.append(stat(sample))
    draws.sort()
    lo = draws[int((1 - level) / 2 * n_boot)]
    hi = draws[min(n_boot - 1, int((1 + level) / 2 * n_boot))]
    return {"point": point, "ci_low": lo, "ci_high": hi, "n_firms": len(firms), "n_boot": n_boot}


def paired_difference(stat_treatment: Callable[[list], float], stat_control: Callable[[list], float],
                      groups: Mapping[str, Sequence], n_boot: int = 2000, seed: int = 0,
                      one_sided_lower: bool = False) -> dict:
    """Bootstrap the difference treatment - control over the same resampled firms.

    With ``one_sided_lower`` the 95% lower bound is returned (used for the withholding
    tolerance: sensitivity and coverage must not fall more than five points below arm B).
    """
    rng = random.Random(seed)
    firms = list(groups)
    all_units = [u for f in firms for u in groups[f]]
    point = stat_treatment(all_units) - stat_control(all_units)
    draws = []
    for _ in range(n_boot):
        sample = []
        for _ in firms:
            sample.extend(groups[rng.choice(firms)])
        draws.append(stat_treatment(sample) - stat_control(sample))
    draws.sort()
    if one_sided_lower:
        return {"point": point, "lower_95": draws[int(0.05 * n_boot)], "n_firms": len(firms)}
    return {"point": point, "ci_low": draws[int(0.025 * n_boot)], "ci_high": draws[min(n_boot - 1, int(0.975 * n_boot))],
            "n_firms": len(firms)}
