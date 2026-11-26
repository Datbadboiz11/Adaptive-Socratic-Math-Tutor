"""Fit on train and evaluate dev; open held-out test only with --evaluate-test."""
from __future__ import annotations

import argparse
import csv
import json
import platform
from collections import Counter, defaultdict, deque
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
    skill_state, pooled_state = {}, {}
    histories = defaultdict(lambda: deque(maxlen=5))
    output = []
    for row in rows:
        skill, student, y = row["skill_id"], row["student_id"], row["correct"]
        key = (student, skill)
        skill_params = models.get(skill, pooled)["parameters"]
        pooled_params = pooled["parameters"]
        skill_prior = skill_state.get(key, skill_params["prior"])
        pooled_prior = pooled_state.get(key, pooled_params["prior"])
        skill_prediction, skill_after = step(skill_prior, y, skill_params)
        pooled_prediction, pooled_after = step(pooled_prior, y, pooled_params)
        rate = skill_rates.get(skill, global_rate)
        history = histories[student]
        historical = sum(history) / len(history) if history else global_rate
        output.append({**row, "bkt": skill_prediction, "bkt_per_skill": skill_prediction,
                       "bkt_pooled": pooled_prediction, "majority_rate": global_rate,
                       "skill_rate": rate, "history_rate": historical,
                       "history_count": len(history), "mastery_before": skill_prior,
                       "mastery_after": skill_after,
                       "parameter_source": models.get(skill, {}).get("source", "pooled_unseen_skill")})
        skill_state[key] = skill_after
        pooled_state[key] = pooled_after
        history.append(y)
    result = {}
    for name in ("bkt_per_skill", "bkt_pooled", "majority_rate", "skill_rate", "history_rate"):
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
    # Preserve the existing result key for downstream reports/tests.
    result["bkt"] = result["bkt_per_skill"]
    return result, output


def _markdown_report(dev_results: dict, test_results: dict | None) -> str:
    labels = (
        ("bkt_pooled", "Pooled BKT"),
        ("bkt_per_skill", "Per-skill BKT"),
        ("majority_rate", "Majority class"),
        ("skill_rate", "Skill average"),
        ("history_rate", "Moving average (last 5)"),
    )

    def display(value):
        return "—" if value is None else f"{value:.4f}"

    splits = [("dev", dev_results)]
    if test_results is not None:
        splits.append(("test", test_results))
    lines = [
        "## RQ1a: BKT next-outcome prediction",
        "",
        "| Split | Model | N | Log loss (lower) | AUC-ROC (higher) | Brier (lower) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for split, results in splits:
        for key, label in labels:
            micro = results[key]["micro"]
            lines.append(
                f"| {split} | {label} | {micro['observations']} | "
                f"{display(micro['log_loss'])} | {display(micro['auc'])} | {display(micro['brier'])} |"
            )
    lines.extend(["", "### Calibration: expected vs observed", "",
                  "| Split | Model | Probability bin | N | Expected | Observed |",
                  "|---|---|---:|---:|---:|---:|"])
    for split, results in splits:
        for key, label in labels:
            for bucket in results[key]["micro"]["calibration"]:
                if not bucket["n"]:
                    continue
                interval = f"[{bucket['lower']:.1f}, {bucket['upper']:.1f}{']' if bucket['upper'] == 1 else ')'}"
                lines.append(
                    f"| {split} | {label} | {interval} | {bucket['n']} | "
                    f"{display(bucket['mean_prediction'])} | {display(bucket['observed_rate'])} |"
                )
    return "\n".join(lines) + "\n"


def benchmark(processed: Path, output: Path, *, evaluate_test: bool = False) -> dict:
    import numpy
    import scipy
    processed, output = processed.resolve(), output.resolve()
    if output.suffix.lower() == ".json":
        report_path = output
        artifact_dir = output.with_name(output.stem + "_artifacts")
        allow_existing_artifacts = True
    else:
        artifact_dir = output
        report_path = artifact_dir / "benchmark_report.json"
        allow_existing_artifacts = False
    data_root = (ROOT / "data").resolve()
    if (not artifact_dir.is_relative_to(data_root) or not report_path.is_relative_to(data_root)
            or artifact_dir == processed or artifact_dir.is_relative_to(processed)
            or processed.is_relative_to(artifact_dir)):
        raise ValueError("Use report/artifact outputs under data/, separate from preprocessing")
    config = load_config(processed / "protocol.json")
    preprocessing = json.loads((processed / "preprocessing_report.json").read_text(encoding="utf-8"))
    for name in ("train.csv", "dev.csv", "protocol.json", "split_manifest.json"):
        if digest_file(processed / name) != preprocessing["artifact_sha256"][name]:
            raise ValueError(f"Changed preprocessing artifact: {name}")
    train, dev = read_split(processed / "train.csv"), read_split(processed / "dev.csv")
    train_students, dev_students = ({r["student_id"] for r in rows} for rows in (train, dev))
    manifest = json.loads((processed / "split_manifest.json").read_text(encoding="utf-8"))["students"]
    if (train_students & dev_students
            or any(manifest.get(s) != "train" for s in train_students)
            or any(manifest.get(s) != "dev" for s in dev_students)):
        raise ValueError("Student split leakage or manifest mismatch")

    test = None
    if evaluate_test:
        expected_test_hash = preprocessing.get("artifact_sha256", {}).get("test.csv")
        if expected_test_hash is None or digest_file(processed / "test.csv") != expected_test_hash:
            raise ValueError("Missing or changed sealed test artifact")
        test = read_split(processed / "test.csv")
        test_students = {r["student_id"] for r in test}
        if (train_students & test_students or dev_students & test_students
                or any(manifest.get(s) != "test" for s in test_students)):
            raise ValueError("Student test split leakage or manifest mismatch")
    else:
        test_students = set()

    artifact_dir.mkdir(parents=True, exist_ok=allow_existing_artifacts)
    fit_config = config["fit"]
    print(f"Fitting pooled BKT: {len(train)} train observations", flush=True)
    pooled = {**fit(sequences(train), fit_config), "source": "pooled_train"}
    groups = defaultdict(list)
    for row in train:
        groups[row["skill_id"]].append(row)
    total_correct = sum(r["correct"] for r in train)
    global_rate = total_correct / len(train)
    models, rates = {}, {}
    for i, (skill, group) in enumerate(sorted(groups.items()), 1):
        seqs = sequences(group)
        positives = sum(r["correct"] for r in group)
        rates[skill] = positives / len(group)
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
    with (artifact_dir / "dev_predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    test_results, test_predictions = None, None
    if test is not None:
        test_results, test_predictions = evaluate(test, models, pooled, rates, global_rate)
        with (artifact_dir / "test_predictions.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(test_predictions[0]))
            writer.writeheader()
            writer.writerows(test_predictions)
    model_artifact = {"protocol_version": config["protocol_version"], "fit_config": fit_config,
                      "pooled": pooled, "skills": models, "global_rate": global_rate, "skill_rates": rates}
    parameters_path = artifact_dir / "parameters.json"
    parameters_path.write_text(json.dumps(model_artifact, indent=2) + "\n", encoding="utf-8")
    source_counts = dict(Counter(m["source"] for m in models.values()))
    report = {"protocol_version": config["protocol_version"], "evaluation_split": "dev",
              "test_evaluated": test is not None,
              "selection_data": "train only; no dev model selection in v1", "fit_engine": fit_config["engine"],
              "preprocessing_report_sha256": digest_file(processed / "preprocessing_report.json"),
              "parameter_sha256": digest_file(parameters_path),
              "code_sha256": {p.name: digest_file(p) for p in (Path(__file__), ROOT / "research/bkt/model.py", ROOT / "research/bkt/metrics.py")},
              "environment": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__},
              "train_observations": len(train), "dev_observations": len(dev),
              "test_observations": len(test) if test is not None else None,
              "train_students": len(train_students), "dev_students": len(dev_students),
              "test_students": len(test_students) if test is not None else None,
              "model_sources": source_counts,
              "dev_parameter_sources": dict(Counter(r["parameter_source"] for r in predictions)),
              "boundary_skill_fits": sum(bool(m.get("boundary_parameters")) for m in models.values()),
              "pooled_diagnostics": {k: v for k, v in pooled.items() if k != "parameters"},
              "results": results, "test_results": test_results,
              "pybkt_parity": "NOT RUN: optional dependency unavailable",
              "limitations": preprocessing["limitations"] + [
                    "Test is not opened unless --evaluate-test is explicitly supplied.",
                    "Bounds and support thresholds are predeclared engineering choices, not universal BKT standards.",
                    "Moving average uses up to five preceding observed outcomes for each evaluation student; cold start uses train prevalence.",
                    "Learning during excluded help/scaffold is not modeled; later observations may follow instruction.",
                    "MLE may reach a local optimum; no claim that latent mastery is identifiable or calibrated.",
                    "Research parameters are NOT installed into the product or mapped to Vietnamese skills."]}
    markdown = _markdown_report(results, test_results)
    report["markdown_report"] = markdown
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report_path.with_suffix(".md").write_text(markdown, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit train-only BKT and compare next-outcome baselines.")
    parser.add_argument("--processed", type=Path, default=ROOT / "data/processed/assistments2017-v1")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data/experiments/rq1a_kt_benchmark_report.json",
                        help="Report JSON path; prediction/model artifacts are written to a sibling directory")
    parser.add_argument("--evaluate-test", action="store_true",
                        help="Explicitly open held-out test.csv after fitting on train.csv")
    args = parser.parse_args()
    report = benchmark(args.processed, args.output, evaluate_test=args.evaluate_test)
    print(report["markdown_report"])
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
