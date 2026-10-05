"""Fit train-only BKT and evaluate dev. This command never opens test.csv."""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
from collections import Counter, defaultdict
from pathlib import Path

from research.bkt.metrics import metrics
from research.bkt.model import fit, sequences, step
from research.data.preprocess_assistments_2017 import ROOT, digest_file, load_config


def read_split(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    opportunities, previous = set(), {}
    for row in rows:
        row["correct"] = int(row["correct"])
        row["order_id"] = int(row["order_id"])
        if row["correct"] not in (0, 1) or row["opportunity_id"] in opportunities:
            raise ValueError("Invalid label or duplicate opportunity")
        opportunities.add(row["opportunity_id"])
        student = row["student_id"]
        if row["order_id"] <= previous.get(student, -1):
            raise ValueError("Student sequence is not chronologically ordered")
        previous[student] = row["order_id"]
    if not rows:
        raise ValueError("Empty split")
    return rows


def evaluate(rows: list[dict], models: dict, pooled: dict, skill_rates: dict, global_rate: float) -> tuple[dict, list[dict]]:
    state, histories = {}, defaultdict(lambda: [0, 0])
    output = []
    for row in rows:
        skill, student, y = row["skill_id"], row["student_id"], row["correct"]
        key = (student, skill)
        params = models.get(skill, pooled)["parameters"]
        p = state.get(key, params["prior"])
        prediction, after = step(p, y, params)
        rate = skill_rates.get(skill, global_rate)
        successes, n = histories[key]
        # Beta-style shrinkage toward TRAIN rate, using previous DEV answers only.
        historical = (successes + 2 * rate) / (n + 2)
        output.append({**row, "bkt": prediction, "skill_rate": rate, "history_rate": historical,
                       "mastery_before": p, "mastery_after": after,
                       "parameter_source": models.get(skill, {}).get("source", "pooled_unseen_skill")})
        state[key] = after
        histories[key] = [successes + y, n + 1]
    result = {}
    for name in ("bkt", "skill_rate", "history_rate"):
        aggregate = metrics([r["correct"] for r in output], [r[name] for r in output])
        grouped = defaultdict(list)
        for row in output:
            grouped[row["skill_id"]].append(row)
        per_skill = {s: metrics([r["correct"] for r in group], [r[name] for r in group]) for s, group in grouped.items()}
        macro = {}
        for metric in ("log_loss", "brier", "auc"):
            available = [m[metric] for m in per_skill.values() if m[metric] is not None]
            macro[metric] = sum(available) / len(available) if available else None
            macro[metric + "_skills"] = len(available)
        result[name] = {"micro": aggregate, "macro": macro, "per_skill": per_skill}
    return result, output


def benchmark(processed: Path, output: Path) -> dict:
    import numpy
    import scipy
    processed, output = processed.resolve(), output.resolve()
    if not output.is_relative_to(ROOT / "data") or output == processed or output.is_relative_to(processed):
        raise ValueError("Use a fresh output directory under data/, separate from preprocessing")
    config = load_config(processed / "protocol.json")
    preprocessing = json.loads((processed / "preprocessing_report.json").read_text(encoding="utf-8"))
    for name in ("train.csv", "dev.csv", "protocol.json", "split_manifest.json"):
        if digest_file(processed / name) != preprocessing["artifact_sha256"][name]:
            raise ValueError(f"Changed preprocessing artifact: {name}")
    train, dev = read_split(processed / "train.csv"), read_split(processed / "dev.csv")
    train_students, dev_students = ({r["student_id"] for r in rows} for rows in (train, dev))
    manifest = json.loads((processed / "split_manifest.json").read_text(encoding="utf-8"))["students"]
    if train_students & dev_students or any(manifest.get(s) != "train" for s in train_students) or any(manifest.get(s) != "dev" for s in dev_students):
        raise ValueError("Student split leakage or manifest mismatch")
    output.mkdir(parents=True, exist_ok=False)
    fit_config = config["fit"]
    print(f"Fitting pooled BKT: {len(train)} train observations", flush=True)
    pooled = {**fit(sequences(train), fit_config), "source": "pooled_train"}
    groups = defaultdict(list)
    for row in train:
        groups[row["skill_id"]].append(row)
    total_correct = sum(r["correct"] for r in train)
    global_rate = (total_correct + 1) / (len(train) + 2)
    models, rates = {}, {}
    for i, (skill, group) in enumerate(sorted(groups.items()), 1):
        seqs = sequences(group)
        positives = sum(r["correct"] for r in group)
        rates[skill] = (positives + 1) / (len(group) + 2)
        support = {"observations": len(group), "sequences": len(seqs), "positive": positives}
        sufficient = (len(group) >= fit_config["min_observations"] and len(seqs) >= fit_config["min_sequences"]
                      and min(positives, len(group) - positives) >= fit_config["min_each_class"])
        if sufficient:
            try:
                models[skill] = {**fit(seqs, fit_config), "source": "skill_train_mle", "support": support}
            except ValueError:
                models[skill] = {"parameters": pooled["parameters"], "source": "pooled_nonconvergence", "support": support}
        else:
            models[skill] = {"parameters": pooled["parameters"], "source": "pooled_insufficient_support", "support": support}
        print(f"Skill {i}/{len(groups)}: {models[skill]['source']}", flush=True)
    results, predictions = evaluate(dev, models, pooled, rates, global_rate)
    with (output / "dev_predictions.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    model_artifact = {"protocol_version": config["protocol_version"], "fit_config": fit_config,
                      "pooled": pooled, "skills": models, "global_rate": global_rate, "skill_rates": rates}
    (output / "parameters.json").write_text(json.dumps(model_artifact, indent=2) + "\n", encoding="utf-8")
    source_counts = dict(Counter(m["source"] for m in models.values()))
    report = {"protocol_version": config["protocol_version"], "evaluation_split": "dev", "test_evaluated": False,
              "selection_data": "train only; no dev model selection in v1", "fit_engine": fit_config["engine"],
              "preprocessing_report_sha256": digest_file(processed / "preprocessing_report.json"),
              "parameter_sha256": digest_file(output / "parameters.json"),
              "code_sha256": {p.name: digest_file(p) for p in (Path(__file__), ROOT / "research/bkt/model.py", ROOT / "research/bkt/metrics.py")},
              "environment": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__},
              "train_observations": len(train), "dev_observations": len(dev), "train_students": len(train_students),
              "dev_students": len(dev_students), "model_sources": source_counts,
              "dev_parameter_sources": dict(Counter(r["parameter_source"] for r in predictions)),
              "boundary_skill_fits": sum(bool(m.get("boundary_parameters")) for m in models.values()),
              "pooled_diagnostics": {k: v for k, v in pooled.items() if k != "parameters"},
              "results": results, "pybkt_parity": "NOT RUN: optional dependency unavailable",
              "limitations": preprocessing["limitations"] + ["Development results only; no held-out test claims or confidence intervals yet.",
                    "Bounds and support thresholds are predeclared engineering choices, not universal BKT standards.",
                    "Learning during excluded help/scaffold is not modeled; later observations may follow instruction.",
                    "MLE may reach a local optimum; no claim that latent mastery is identifiable or calibrated.",
                    "Research parameters are NOT installed into the product or mapped to Vietnamese skills."]}
    (output / "benchmark_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=ROOT / "data/processed/assistments2017-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "data/experiments/assistments2017-bkt-v1")
    args = parser.parse_args()
    report = benchmark(args.processed, args.output)
    print(json.dumps({name: value["micro"] for name, value in report["results"].items()}, indent=2))


if __name__ == "__main__":
    main()
