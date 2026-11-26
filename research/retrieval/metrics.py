"""Retrieval metrics: direct relevance >=2; graded gain 2**grade-1; undefined => None."""
import math
from statistics import mean


def score(ranking, grades, k):
    if k < 1 or len(ranking) != len(set(ranking)) or set(ranking).difference(grades):
        raise ValueError("Invalid cutoff, duplicate ranking, or unjudged candidate")
    if any(type(grade) is not int or grade not in (0, 1, 2) for grade in grades.values()):
        raise ValueError("Expected integer relevance grades 0, 1 or 2")
    direct = {key for key, grade in grades.items() if grade >= 2}
    selected = ranking[:k]
    found = len(direct.intersection(selected))
    def dcg(values):
        return sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(values))
    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    return {"recall": found / len(direct) if direct else None,
            "hit": float(found > 0) if direct else None,
            "ndcg": dcg([grades[key] for key in selected]) / ideal if ideal else None}


def aggregate(rows):
    return {metric: {"mean": mean(values) if values else None, "defined_queries": len(values),
                     "undefined_queries": len(rows) - len(values)}
            for metric in ("recall", "hit", "ndcg")
            for values in [[row[metric] for row in rows if row[metric] is not None]]}
