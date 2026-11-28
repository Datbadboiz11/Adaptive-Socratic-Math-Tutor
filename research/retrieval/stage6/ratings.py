"""Validate independent paired ratings; unresolved disagreements never become quality claims."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from statistics import mean

from research.retrieval.dataset import json_bytes, normalized, require, sha256
from research.retrieval.stage6.evaluation import quantile
from research.retrieval.stage6.paired_outputs import CRITERIA


def load_run(base):
    base = Path(base).resolve()
    read = lambda name: json.loads((base / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    require(manifest["status"] == "dev_evaluation_completed", "A completed dev run is required")
    require(manifest.get("formal_test_ready") is False, "This rating workflow is for the dev packet")
    require({"paired-blind.json", "paired-key.json", "report.json"}.issubset(manifest["files_sha256"]),
            "Run manifest must pin the packet, key and report")
    for name, expected in manifest["files_sha256"].items():
        target = (base / name).resolve()
        require(target.is_relative_to(base) and target.is_file(), "Invalid result file path")
        require(sha256(target.read_bytes()) == expected, "Run artifact hash mismatch: " + name)
    packet, key = read("paired-blind.json"), read("paired-key.json")
    report = read("report.json")
    require(report["owner"] == "Member 2" and len(report["concept_ids"]) == 13, "Foreign evaluation scope")
    return packet, key, report


def validate_review(review, packet):
    require(review["schema_version"] == "1.0.0" and review["method"] == "independent_human",
            "Independent human rating protocol required")
    require(review["packet_sha256"] == sha256(json_bytes(packet)), "Stale rating packet")
    require(isinstance(review["reviewer"], str) and bool(normalized(review["reviewer"])), "Reviewer identity required")
    require(isinstance(review["reviewed_at"], str), "Actual review timestamp required")
    stamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    require(stamp.tzinfo is not None and stamp <= datetime.now(timezone.utc), "Invalid review timestamp")
    require(review["criteria"] == CRITERIA, "Rating rubric changed")
    scenarios = {row["pair_id"]: row for row in packet["pairs"]}
    require(len(scenarios) == len(packet["pairs"]), "Duplicate packet pair")
    seen, scores = set(), {}
    for row in review["pairs"]:
        pid = row["pair_id"]
        require(pid in scenarios and pid not in seen, "Unknown or duplicate rated pair")
        seen.add(pid)
        require(set(row["responses"]) == {"A", "B"}, "Both blinded responses must be rated")
        for label, response in row["responses"].items():
            require(set(response["scores"]) == set(CRITERIA), "Incomplete rating criteria")
            for criterion, score in response["scores"].items():
                applicable = criterion != "error_alignment" or scenarios[pid]["error_alignment_applicable"]
                require(type(score) is int and score in (0, 1, 2) if applicable else score is None,
                        "Missing/invalid rating or a score assigned to N/A")
                scores[(pid, label, criterion)] = score
    require(seen == set(scenarios), "Incomplete paired rating coverage")
    return scores


def compare_reviews(first, second, packet, key, *, seed=20261126, samples=1000):
    require(normalized(first.get("reviewer") or "") != normalized(second.get("reviewer") or ""),
            "Two different independent reviewers required")
    left, right = validate_review(first, packet), validate_review(second, packet)
    conflicts = [{"pair_id": pid, "response": label, "criterion": criterion, "first": score,
                  "second": right[(pid, label, criterion)]}
                 for (pid, label, criterion), score in left.items() if score != right[(pid, label, criterion)]]
    by_pair = {row["pair_id"]: row for row in key}
    require(len(by_pair) == len(key) and set(by_pair) == {row["pair_id"] for row in packet["pairs"]},
            "Packet key coverage mismatch")
    require(all(set(row["configuration_by_label"]) == {"A", "B"}
                and set(row["configuration_by_label"].values()) == {"full", "no_rag"} for row in key),
            "Invalid blinded configuration mapping")
    agreement = {}
    for criterion in CRITERIA:
        keys = [value for value, score in left.items() if value[2] == criterion and score is not None]
        count = len(keys)
        observed = mean(left[value] == right[value] for value in keys) if keys else None
        a, b = Counter(left[value] for value in keys), Counter(right[value] for value in keys)
        chance = sum(a[grade] * b[grade] for grade in (0, 1, 2)) / count**2 if count else None
        agreement[criterion] = {"rated_responses": count, "exact_agreement": observed,
                               "cohen_kappa": (observed - chance) / (1 - chance) if chance is not None and chance < 1 else None}
    summary = None
    if not conflicts:
        summary = {}
        for criterion in CRITERIA:
            clusters, values = defaultdict(list), {"full": [], "no_rag": []}
            for pid, mapping in by_pair.items():
                scores = {mode: left[(pid, label, criterion)] for label, mode in mapping["configuration_by_label"].items()}
                if scores["full"] is None:
                    continue
                for mode, score in scores.items():
                    values[mode].append(score)
                delta = scores["full"] - scores["no_rag"]
                clusters[mapping["concept_id"]].append(-delta if criterion == "answer_disclosure" else delta)
            ids = sorted(clusters)
            rng = random.Random(seed)
            draws = [mean(value for _ in ids for value in clusters[rng.choice(ids)]) for _ in range(samples)] if ids else []
            deltas = [value for rows in clusters.values() for value in rows]
            summary[criterion] = {"paired_scenarios": len(deltas), "concept_clusters": len(ids),
                "mean_by_configuration": {mode: mean(scores) if scores else None for mode, scores in values.items()},
                "improvement_for_full": mean(deltas) if deltas else None,
                "ci95": [quantile(draws, .025), quantile(draws, .975)],
                "direction": "no_rag_minus_full_lower_disclosure_is_better" if criterion == "answer_disclosure" else "full_minus_no_rag"}
    return {"status": "needs_adjudication" if conflicts else "agreed", "packet_sha256": sha256(json_bytes(packet)),
            "reviewers": [first["reviewer"], second["reviewer"]], "agreement": agreement,
            "conflicts": conflicts, "quality_summary": summary, "formal_test_ready": False,
            "note": "Independent ratings of authoring/dev scenarios; a final test still requires independent scenarios and frozen inputs."}
