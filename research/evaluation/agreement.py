"""Độ đồng thuận giữa hai người chấm và khoảng tin cậy bootstrap (plan §19.2, §19.3).

- ``cohen_kappa``: nhãn phân loại (cờ nghiêm trọng, không chấm được, lựa chọn ghép cặp).
- ``weighted_kappa``: điểm thứ bậc 0–2 của từng chiều; mặc định trọng số bậc hai.
- ``bootstrap_mean_ci``: lấy mẫu lại theo **tình huống**, không theo từng câu, vì các câu của cùng
  tình huống không độc lập (plan §19.3 bước 5).

Không phụ thuộc thư viện ngoài. Trả ``None`` khi chỉ số không xác định (không có mẫu, hoặc mọi
người chấm cùng chọn một nhãn nên đồng thuận ngẫu nhiên bằng 1).
"""
from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
import random
from typing import Literal

Weights = Literal["linear", "quadratic"]


def _proportions(values: Sequence[Hashable], categories: Sequence[Hashable]) -> list[float]:
    return [sum(v == c for v in values) / len(values) for c in categories]


def _check(a: Sequence, b: Sequence, categories: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError("both raters must label the same items")
    unknown = (set(a) | set(b)) - set(categories)
    if unknown:
        raise ValueError(f"labels outside the categories: {sorted(map(str, unknown))}")


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable],
                categories: Sequence[Hashable] | None = None) -> float | None:
    categories = list(categories) if categories is not None else sorted(set(a) | set(b), key=str)
    _check(a, b, categories)
    if not a:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    expected = sum(pa * pb for pa, pb in zip(_proportions(a, categories), _proportions(b, categories)))
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def weighted_kappa(a: Sequence[Hashable], b: Sequence[Hashable], categories: Sequence[Hashable],
                   weights: Weights = "quadratic") -> float | None:
    """``categories`` theo thứ tự thứ bậc. Trọng số bất đồng: |i - j|/(k - 1), bình phương nếu quadratic."""
    _check(a, b, categories)
    k = len(categories)
    if not a or k < 2:
        return None
    index = {c: i for i, c in enumerate(categories)}
    power = 2 if weights == "quadratic" else 1

    def w(i: int, j: int) -> float:
        return (abs(i - j) / (k - 1)) ** power

    observed = sum(w(index[x], index[y]) for x, y in zip(a, b)) / len(a)
    pa, pb = _proportions(a, categories), _proportions(b, categories)
    expected = sum(w(i, j) * pa[i] * pb[j] for i in range(k) for j in range(k))
    if expected == 0:
        return None
    return 1 - observed / expected


def bootstrap_mean_ci(groups: Mapping[Hashable, Sequence[float]], *, resamples: int = 2000, seed: int = 0,
                      level: float = 0.95) -> tuple[float, float] | None:
    """Khoảng tin cậy percentile của giá trị trung bình, lấy mẫu lại theo nhóm (tình huống)."""
    keys = [k for k, values in groups.items() if values]
    if not keys:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        values = [v for k in rng.choices(keys, k=len(keys)) for v in groups[k]]
        means.append(sum(values) / len(values))
    means.sort()
    tail = (1 - level) / 2
    return means[int(tail * (resamples - 1))], means[int((1 - tail) * (resamples - 1))]
