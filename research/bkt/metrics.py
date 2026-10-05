"""Binary probability metrics with explicit tie handling and undefined AUC."""
import math


def metrics(targets: list[int], predictions: list[float]) -> dict:
    if not targets or len(targets) != len(predictions):
        raise ValueError("Nonempty, aligned inputs required")
    if any(y not in (0, 1) for y in targets) or any(not math.isfinite(p) or not 0 <= p <= 1 for p in predictions):
        raise ValueError("Invalid binary labels/probabilities")
    n, positive = len(targets), sum(targets)
    bins = [{"n": 0, "sum_p": 0.0, "sum_y": 0} for _ in range(10)]
    log_loss, brier = 0.0, 0.0
    for y, p in zip(targets, predictions):
        clipped = min(1 - 1e-12, max(1e-12, p))
        log_loss -= math.log(clipped if y else 1 - clipped)
        brier += (p - y) ** 2
        bucket = bins[min(9, int(p * 10))]
        bucket["n"] += 1
        bucket["sum_p"] += p
        bucket["sum_y"] += y
    auc = None
    if 0 < positive < n:
        ordered = sorted(zip(predictions, targets))
        i, positive_rank = 0, 0.0
        while i < n:
            j = i + 1
            while j < n and ordered[j][0] == ordered[i][0]:
                j += 1
            positive_rank += ((i + 1 + j) / 2) * sum(y for _, y in ordered[i:j])
            i = j
        auc = (positive_rank - positive * (positive + 1) / 2) / (positive * (n - positive))
    calibration = [{"lower": i / 10, "upper": (i + 1) / 10, "n": b["n"],
                    "mean_prediction": b["sum_p"] / b["n"] if b["n"] else None,
                    "observed_rate": b["sum_y"] / b["n"] if b["n"] else None}
                   for i, b in enumerate(bins)]
    ece = sum(abs(b["sum_p"] - b["sum_y"]) for b in bins) / n
    return {"observations": n, "positive": positive, "log_loss": log_loss / n,
            "brier": brier / n, "auc": auc, "ece_10_equal_width": ece, "calibration": calibration}
