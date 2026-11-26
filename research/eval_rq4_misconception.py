"""Evaluate step localization and misconception diagnosis on the RQ4 benchmark.

Run from the repository root with::

    python research/eval_rq4_misconception.py

The evaluator uses only the hand-authored benchmark and the deterministic
``math_validator.validate`` API.  It does not use learner/LLM explanations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.math_validator import VERSION, validate  # noqa: E402
from app.misconceptions import MISCONCEPTION_CATALOG  # noqa: E402

DEFAULT_DATASET = ROOT / "data" / "evaluation" / "step_errors_benchmark.json"
DEFAULT_REPORT = ROOT / "data" / "experiments" / "rq4_evaluation_report.json"
DEFAULT_MARKDOWN = ROOT / "data" / "experiments" / "rq4_evaluation_report.md"
ABSTENTION_STATUSES = {"unverified", "needs_clarification"}

# Catalog IDs are fine-grained detectors.  RQ4 reports their broader reasoning
# family so that related algebraic misconceptions share one classification.
ERROR_FAMILY = {
    "M_DIST_01": "distribution_missing_term",
    "M_EQ_DIST_01": "distribution_missing_term",
    "M_DIST_02": "negative_distribution_sign",
    "M_EQ_DIST_02": "negative_distribution_sign",
    "M_SQUARE_01": "square_missing_middle_term",
    "M_SQUARE_02": "square_identity_confusion",
    "M_POLY_01": "binomial_missing_cross_terms",
    "M_POLY_02": "binomial_constant_sign",
    "M_LIKE_01": "like_terms_multiplied",
    "M_LIKE_02": "integer_sign_arithmetic",
    "M_FACTOR_01": "incomplete_common_factor",
    "M_FACTOR_02": "incomplete_common_factor",
    "M_DIFFSQ_01": "difference_of_squares_sign",
    "M_DIFFSQ_02": "difference_of_squares_confusion",
    "M_EQ_01": "one_sided_equation_operation",
    "M_EQ_02": "negative_coefficient_sign",
    "M_INV_01": "inverse_operation",
    "M_SIGN_01": "negative_coefficient_sign",
    "M_ZERO_01": "missing_product_branch",
    "M_ZERO_02": "dividing_out_possible_zero_factor",
    "M_DOMAIN_01": "lost_domain_restriction",
    "M_DOMAIN_02": "accepted_excluded_root",
    "M_QUAD_01": "missing_quadratic_root",
    "M_QUAD_02": "quadratic_root_sign",
}


def _catalog_error_ids() -> set[str]:
    return {
        entry["error_id"]
        for entries in MISCONCEPTION_CATALOG.values()
        for entry in entries
    }


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    raw = path.read_bytes()
    document = json.loads(raw)
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must contain a non-empty cases array")
    category_counts = Counter(case.get("category") for case in cases)
    for category in ("correct", "slip", "misconception"):
        if category_counts[category] < 20:
            raise ValueError(f"RQ4 benchmark needs at least 20 {category} cases; found {category_counts[category]}")
    if not (category_counts["out_of_scope"] + category_counts["ambiguous"] + category_counts["abstention"]):
        raise ValueError("RQ4 benchmark needs out-of-scope or ambiguous cases to measure abstention")
    ids: set[str] = set()
    catalog_ids = _catalog_error_ids()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in ids:
            raise ValueError(f"Missing or duplicate case_id: {case_id!r}")
        ids.add(case_id)
        if not isinstance(case.get("problem"), dict) or not isinstance(case.get("steps"), list):
            raise ValueError(f"Malformed problem or steps in {case_id}")
        if case["category"] in {"slip", "misconception"}:
            expected_step = case.get("expected", {}).get("first_error_step")
            if not isinstance(expected_step, int) or expected_step < 1:
                raise ValueError(f"Incorrect case {case_id} needs a 1-based first_error_step")
        if case["category"] == "misconception":
            error_id = case.get("expected", {}).get("error_id")
            if error_id not in catalog_ids:
                raise ValueError(f"Unknown ground-truth catalog ID {error_id!r} in {case_id}")
            if error_id not in ERROR_FAMILY:
                raise ValueError(f"No RQ4 family mapping for catalog ID {error_id!r}")
            if case["expected"].get("misconception_family") != ERROR_FAMILY[error_id]:
                raise ValueError(f"Family does not match {error_id} in {case_id}")
    return document, cases, hashlib.sha256(raw).hexdigest()


def _family_for_assessment(assessment: dict[str, Any]) -> str:
    candidate = assessment.get("misconception_candidate")
    return ERROR_FAMILY.get(candidate, "unknown")


def _classification_metrics(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        (case, result)
        for case, result in zip(cases, results)
        if case["category"] == "misconception"
    ]
    gold_labels = sorted({case["expected"]["misconception_family"] for case, _ in scored})
    labels = gold_labels + (["unknown"] if "unknown" not in gold_labels else [])
    confusion = {gold: {predicted: 0 for predicted in labels} for gold in labels}
    predicted_families = []
    true_families = []
    for case, result in scored:
        gold = case["expected"]["misconception_family"]
        predicted = result["actual"]["misconception_family"]
        if predicted not in confusion[gold]:
            predicted = "unknown"
        confusion[gold][predicted] += 1
        true_families.append(gold)
        predicted_families.append(predicted)

    per_family: dict[str, Any] = {}
    f1_values: list[float] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    for label in gold_labels:
        tp = sum(1 for gold, pred in zip(true_families, predicted_families) if gold == label and pred == label)
        fp = sum(1 for gold, pred in zip(true_families, predicted_families) if gold != label and pred == label)
        fn = sum(1 for gold, pred in zip(true_families, predicted_families) if gold == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        support = sum(1 for gold in true_families if gold == label)
        per_family[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1)

    return {
        "evaluated_cases": len(scored),
        "macro_precision": sum(precision_values) / len(precision_values) if precision_values else None,
        "macro_recall": sum(recall_values) / len(recall_values) if recall_values else None,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "per_family": per_family,
        "confusion_matrix": {
            "labels": labels,
            "rows_are": "ground_truth",
            "columns_are": "prediction",
            "counts": confusion,
        },
    }


def evaluate(document: dict[str, Any], cases: list[dict[str, Any]], dataset_sha256: str) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    for case in cases:
        raw_result = validate(case["problem"], case["steps"])
        assessment = raw_result["assessment"]
        actual = {
            "assessment_status": assessment["assessment_status"],
            "first_error_step": assessment["first_error_step"],
            "misconception_candidate": assessment["misconception_candidate"],
            "misconception_family": _family_for_assessment(assessment),
            "diagnosis_status": assessment["diagnosis_status"],
            "reason_code": assessment["reason_code"],
        }
        expected = case["expected"]
        matches = {
            "assessment_status": actual["assessment_status"] == expected.get("assessment_status"),
            "first_error_step": actual["first_error_step"] == expected.get("first_error_step"),
        }
        if case["category"] == "misconception":
            matches["error_id"] = actual["misconception_candidate"] == expected["error_id"]
        case_results.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "expected": expected,
            "actual": actual,
            "matches": matches,
        })

    incorrect_cases = [
        (case, result)
        for case, result in zip(cases, case_results)
        if case["category"] in {"slip", "misconception"}
    ]
    localized = sum(
        result["actual"]["first_error_step"] == case["expected"]["first_error_step"]
        for case, result in incorrect_cases
    )
    correct_cases = [(case, result) for case, result in zip(cases, case_results) if case["category"] == "correct"]
    correctly_verified = sum(result["actual"]["assessment_status"] == "verified_correct" for _, result in correct_cases)
    abstention_cases = [
        result for case, result in zip(cases, case_results)
        if case["category"] in {"out_of_scope", "ambiguous", "abstention"}
    ]
    abstained = sum(result["actual"]["assessment_status"] in ABSTENTION_STATUSES for result in abstention_cases)
    slip_results = [
        result for case, result in zip(cases, case_results) if case["category"] == "slip"
    ]
    slip_false_positives = sum(
        result["actual"]["misconception_family"] != "unknown" for result in slip_results
    )
    category_counts = Counter(case["category"] for case in cases)
    status_matches = sum(result["matches"]["assessment_status"] for result in case_results)
    all_expected_matches = sum(all(result["matches"].values()) for result in case_results)

    return {
        "report_version": "rq4-step-errors-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": (str(DEFAULT_DATASET.relative_to(ROOT)) if document.get("_source_path") is None
                     else document["_source_path"].replace("\\", "/")),
            "sha256": dataset_sha256,
            "language": document.get("language", "vi"),
            "benchmark_type": document.get("benchmark_type", "unspecified"),
            "limitations": document.get("limitations_vi"),
            "case_count": len(cases),
            "category_counts": dict(sorted(category_counts.items())),
            "required_core_cases": {"correct": 20, "slip": 20, "misconception": 20},
        },
        "validator": {"api": "app.math_validator.validate", "version": VERSION},
        "metrics": {
            "step_localization": {
                "correct": localized,
                "total_incorrect_cases": len(incorrect_cases),
                "accuracy": localized / len(incorrect_cases) if incorrect_cases else None,
                "percentage": 100 * localized / len(incorrect_cases) if incorrect_cases else None,
                "indexing": "1-based; exact first_error_step match",
            },
            "correct_solution_verification": {
                "verified_correct": correctly_verified,
                "total_correct_cases": len(correct_cases),
                "rate": correctly_verified / len(correct_cases) if correct_cases else None,
            },
            "benchmark_label_match": {
                "status_matches": status_matches,
                "all_expected_labels_match": all_expected_matches,
                "total_cases": len(case_results),
                "status_accuracy": status_matches / len(case_results) if case_results else None,
                "exact_label_accuracy": all_expected_matches / len(case_results) if case_results else None,
            },
            "misconception_classification": _classification_metrics(cases, case_results),
            "arithmetic_slip_diagnosis": {
                "false_positive_known_misconception": slip_false_positives,
                "total_arithmetic_slips": len(slip_results),
                "false_positive_rate": slip_false_positives / len(slip_results) if slip_results else None,
                "unclassified_as_known_misconception": len(slip_results) - slip_false_positives,
            },
            "abstention": {
                "abstained": abstained,
                "total_out_of_scope_or_ambiguous": len(abstention_cases),
                "rate": abstained / len(abstention_cases) if abstention_cases else None,
                "accepted_statuses": sorted(ABSTENTION_STATUSES),
            },
        },
        "case_results": case_results,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    localization = metrics["step_localization"]
    classification = metrics["misconception_classification"]
    abstention = metrics["abstention"]
    lines = [
        "# RQ4: Step Error and Misconception Evaluation",
        "",
        f"- Dataset: `{report['dataset']['path']}` ({report['dataset']['case_count']} cases)",
        f"- Validator: `{report['validator']['api']}` (`{report['validator']['version']}`)",
        "- Misconception classification is scored on structural-misconception cases only; labels are broad families mapped from catalog error IDs.",
        "- Step numbers are 1-based. Abstention is scored on out-of-scope or ambiguous cases.",
        f"- Limitation: {report['dataset']['limitations'] or 'not specified'}",
        "",
        "## Summary",
        "",
        "| Metric | Result | Numerator / denominator |",
        "|---|---:|---:|",
        f"| Step localization accuracy | {_pct(localization['accuracy'])} | {localization['correct']} / {localization['total_incorrect_cases']} incorrect cases |",
        f"| Correct-solution verification | {_pct(metrics['correct_solution_verification']['rate'])} | {metrics['correct_solution_verification']['verified_correct']} / {metrics['correct_solution_verification']['total_correct_cases']} correct cases |",
        f"| Expected status match | {_pct(metrics['benchmark_label_match']['status_accuracy'])} | {metrics['benchmark_label_match']['status_matches']} / {metrics['benchmark_label_match']['total_cases']} cases |",
        f"| Misconception macro precision | {_pct(classification['macro_precision'])} | {classification['evaluated_cases']} structural cases |",
        f"| Misconception macro recall | {_pct(classification['macro_recall'])} | {classification['evaluated_cases']} structural cases |",
        f"| Misconception macro-F1 | {_pct(classification['macro_f1'])} | {classification['evaluated_cases']} structural cases |",
        f"| Arithmetic-slip false-positive rate | {_pct(metrics['arithmetic_slip_diagnosis']['false_positive_rate'])} | {metrics['arithmetic_slip_diagnosis']['false_positive_known_misconception']} / {metrics['arithmetic_slip_diagnosis']['total_arithmetic_slips']} slips assigned a known misconception |",
        f"| Abstention rate | {_pct(abstention['rate'])} | {abstention['abstained']} / {abstention['total_out_of_scope_or_ambiguous']} out-of-scope/ambiguous cases |",
        "",
        "## Per-family classification",
        "",
        "| Misconception family | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, scores in classification["per_family"].items():
        lines.append(
            f"| `{family}` | {_pct(scores['precision'])} | {_pct(scores['recall'])} | {_pct(scores['f1'])} | {scores['support']} |"
        )
    matrix = classification["confusion_matrix"]
    lines.extend([
        "",
        "## Confusion matrix",
        "",
        "Rows are ground truth; columns are predicted family. `unknown` means the validator did not return a catalog family.",
        "",
        "| Ground truth \\ Prediction | " + " | ".join(f"`{label}`" for label in matrix["labels"]) + " |",
        "|---|" + "---:|" * len(matrix["labels"]),
    ])
    for gold in matrix["labels"]:
        lines.append("| `" + gold + "` | " + " | ".join(str(matrix["counts"][gold][pred]) for pred in matrix["labels"]) + " |")
    lines.extend(["", "## Dataset composition", "", "| Category | Cases |", "|---|---:|"])
    for category, count in report["dataset"]["category_counts"].items():
        lines.append(f"| `{category}` | {count} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    document, cases, digest = load_dataset(args.dataset)
    document["_source_path"] = str(args.dataset.resolve().relative_to(ROOT)) if args.dataset.resolve().is_relative_to(ROOT) else str(args.dataset)
    report = evaluate(document, cases, digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rendered = markdown_report(report)
    args.markdown.write_text(rendered, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    print(rendered)
    print(f"\nJSON report: {args.output}")
    print(f"Markdown report: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
