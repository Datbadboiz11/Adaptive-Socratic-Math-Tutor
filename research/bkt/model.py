"""Constrained maximum likelihood for a no-forgetting two-state BKT model.

The optimized likelihood is the product of predictions BEFORE each observation.
Analytic gradients allow a disk-preprocessed full dataset to fit without pyBKT's
slow Windows EM backend. pyBKT parity is provided separately and remains optional.
"""
from __future__ import annotations

import math
from collections import defaultdict


def step(prior: float, correct: int, parameters: dict) -> tuple[float, float]:
    if correct not in (0, 1):
        raise ValueError("Binary observation required")
    g, s, t = (parameters[k] for k in ("guess", "slip", "learn"))
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (prior, g, s, t)) or g >= 1 - s:
        raise ValueError("Invalid probabilities or indistinguishable/reversed emissions")
    prediction = prior * (1 - s) + (1 - prior) * g
    likelihood = prediction if correct else 1 - prediction
    if likelihood <= 0:
        raise ValueError("Impossible observation")
    posterior = prior * ((1 - s) if correct else s) / likelihood
    return prediction, posterior + (1 - posterior) * t


def sequences(rows: list[dict]) -> list[list[int]]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["student_id"], row["skill_id"])].append(row["correct"])
    return list(groups.values())


def pack(seqs: list[list[int]]):
    import numpy as np
    ordered = sorted((s for s in seqs if s), key=len, reverse=True)
    if not ordered:
        raise ValueError("Empty training sequences")
    # Store only observed cells, not a padded student x maximum length matrix.
    steps = []
    active = len(ordered)
    for i in range(len(ordered[0])):
        while active and len(ordered[active - 1]) <= i:
            active -= 1
        steps.append(np.array([s[i] for s in ordered[:active]], dtype=np.float64))
    return len(ordered), steps, sum(map(len, ordered))


def likelihood_gradient(theta, packed):
    import numpy as np
    count, steps, observations = packed
    prior, learn, guess, slip = theta
    p = np.full(count, prior)
    derivative = np.zeros((count, 4))
    derivative[:, 0] = 1
    loss, gradient = 0.0, np.zeros(4)
    for y in steps:
        n = len(y)
        current = p[:n]
        dp = derivative[:n]
        q = current * (1 - slip) + (1 - current) * guess
        dq = dp * (1 - slip - guess)
        dq[:, 2] += 1 - current
        dq[:, 3] -= current
        sign = 2 * y - 1
        probability = np.where(y == 1, q, 1 - q)
        dr = sign[:, None] * dq
        loss -= np.log(probability).sum()
        gradient -= (dr / probability[:, None]).sum(axis=0)
        emission = np.where(y == 1, 1 - slip, slip)
        posterior = current * emission / probability
        dh = dp * emission[:, None]
        dh[:, 3] += current * (-sign)
        dh = dh / probability[:, None] - posterior[:, None] * dr / probability[:, None]
        derivative[:n] = (1 - learn) * dh
        derivative[:n, 1] += 1 - posterior
        p[:n] = posterior + (1 - posterior) * learn
    return float(loss / observations), gradient / observations


def fit(seqs: list[list[int]], config: dict) -> dict:
    import numpy as np
    from scipy.optimize import minimize
    packed = pack(seqs)
    diagnostics, accepted = [], []
    for start in config["starts"]:
        result = minimize(likelihood_gradient, start, args=(packed,), jac=True,
                          method="L-BFGS-B", bounds=config["bounds"],
                          options={"maxiter": config["max_iterations"], "ftol": 1e-10, "gtol": 1e-7})
        finite = np.isfinite(result.fun) and np.isfinite(result.x).all()
        diagnostics.append({"converged": bool(result.success and finite), "iterations": int(result.nit),
                            "train_log_loss": float(result.fun) if finite else None})
        if result.success and finite:
            accepted.append(result)
    if not accepted:
        raise ValueError("No fit initialization converged")
    best = min(accepted, key=lambda r: r.fun)
    parameters = dict(zip(config["parameter_order"], map(float, best.x)))
    parameters["forget"] = 0.0
    return {"parameters": parameters, "train_log_loss": float(best.fun), "starts": diagnostics,
            "boundary_parameters": [k for k, v, (lo, hi) in zip(config["parameter_order"], best.x, config["bounds"])
                                    if min(abs(v - lo), abs(v - hi)) < 1e-5]}
