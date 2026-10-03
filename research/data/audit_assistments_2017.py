"""Audit the local ASSISTments 2017 competition training logs without exporting student rows.

This is a schema and quality audit, not a BKT training pipeline. In particular,
the competition's training_label.csv is not an event-level correctness label.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


REQUIRED_LOG_COLUMNS = {
    "ITEST_id", "actionId", "skill", "problemId", "startTime", "correct",
    "original", "hint", "hintCount", "scaffold", "attemptCount",
}
FLAG_COLUMNS = ("correct", "original", "hint", "scaffold", "attemptCount")


def find_training_dir(data_root: Path) -> Path:
    matches = list(data_root.rglob("student_log_1.csv"))
    if len(matches) != 1:
        raise ValueError(f"Expected one ASSISTments training directory; found {len(matches)}")
    return matches[0].parent


def _label_ids(path: Path) -> tuple[dict[str, object], set[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if "ITEST_id" not in columns:
            raise ValueError(f"{path.name}: missing ITEST_id")
        ids: set[str] = set()
        rows = 0
        missing_ids = 0
        duplicate_ids = 0
        for row in reader:
            rows += 1
            student = (row["ITEST_id"] or "").strip()
            if not student:
                missing_ids += 1
            elif student in ids:
                duplicate_ids += 1
            else:
                ids.add(student)
    return {
        "file": path.name,
        "rows": rows,
        "columns": columns,
        "unique_students": len(ids),
        "missing_student_ids": missing_ids,
        "duplicate_student_ids": duplicate_ids,
    }, ids


def _flag_bucket(name: str, value: str | None) -> str:
    """Keep unexpected raw values out of a report that may be committed."""
    value = (value or "").strip()
    if not value:
        return "<missing>"
    if name == "attemptCount":
        try:
            count = int(value)
        except ValueError:
            return "<invalid>"
        return str(count) if 0 <= count <= 3 else ("4+" if count > 3 else "<invalid>")
    return value if value in {"0", "1"} else "<invalid>"


def audit_dataset(data_root: Path, max_rows_per_file: int | None = None) -> dict[str, object]:
    if max_rows_per_file is not None and max_rows_per_file < 1:
        raise ValueError("max_rows_per_file must be positive")
    training_dir = find_training_dir(data_root)
    log_files = sorted(
        training_dir.glob("student_log_*.csv"),
        key=lambda path: int(path.stem.removeprefix("student_log_")),
    )
    if not log_files or [path.stem for path in log_files] != [
        f"student_log_{i}" for i in range(1, len(log_files) + 1)
    ]:
        raise ValueError("Training logs are missing or not consecutively numbered from 1")

    students: set[str] = set()
    skills: set[str] = set()
    problems: set[str] = set()
    total = Counter()
    file_stats: list[dict[str, object]] = []
    reference_columns: list[str] | None = None
    case_only_schema_variants: dict[str, list[dict[str, str]]] = {}
    for path in log_files:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            missing_columns = REQUIRED_LOG_COLUMNS.difference(columns)
            if missing_columns:
                raise ValueError(f"{path.name}: missing columns {sorted(missing_columns)}")
            if reference_columns is None:
                reference_columns = columns
            elif columns != reference_columns:
                if [name.casefold() for name in columns] != [name.casefold() for name in reference_columns]:
                    raise ValueError(f"{path.name}: schema differs from student_log_1.csv beyond letter case")
                case_only_schema_variants[path.name] = [
                    {"reference": expected, "actual": actual}
                    for expected, actual in zip(reference_columns, columns)
                    if expected != actual
                ]

            counts = Counter()
            flags = {name: Counter() for name in FLAG_COLUMNS}
            last_time_by_student: dict[str, int] = {}
            for row in reader:
                if max_rows_per_file is not None and counts["rows"] >= max_rows_per_file:
                    break
                counts["rows"] += 1
                if None in row:
                    counts["malformed_rows"] += 1
                    continue
                student = (row["ITEST_id"] or "").strip()
                skill = (row["skill"] or "").strip()
                problem = (row["problemId"] or "").strip()
                timestamp = (row["startTime"] or "").strip()
                if student:
                    students.add(student)
                else:
                    counts["missing_student"] += 1
                if skill:
                    skills.add(skill)
                else:
                    counts["missing_skill"] += 1
                if problem:
                    problems.add(problem)
                else:
                    counts["missing_problem"] += 1
                try:
                    time_value = int(timestamp)
                except ValueError:
                    counts["missing_or_invalid_time"] += 1
                else:
                    if student:
                        previous = last_time_by_student.get(student)
                        if previous is not None and time_value < previous:
                            counts["time_regressions_in_file_order"] += 1
                        last_time_by_student[student] = time_value
                for name in FLAG_COLUMNS:
                    flags[name][_flag_bucket(name, row[name])] += 1
                if row["correct"] not in {"0", "1"}:
                    counts["invalid_or_missing_correct"] += 1
            total.update(counts)
            file_stats.append({
                "file": path.name,
                "size_bytes": path.stat().st_size,
                "counts": dict(sorted(counts.items())),
                "field_values": {name: dict(sorted(values.items())) for name, values in flags.items()},
            })

    labels: dict[str, dict[str, object]] = {}
    label_sets: dict[str, set[str]] = {}
    for name in ("training_label.csv", "validation_test_label.csv"):
        path = training_dir / name
        if not path.is_file():
            raise ValueError(f"Missing {name}")
        labels[name], label_sets[name] = _label_ids(path)
        labels[name]["students_in_logs"] = len(students & label_sets[name])

    return {
        "dataset": "ASSISTments 2017 competition training set",
        "source_directory": training_dir.relative_to(data_root).as_posix(),
        "sampled": max_rows_per_file is not None,
        "max_rows_per_file": max_rows_per_file,
        "log_columns": reference_columns,
        "case_only_schema_variants": case_only_schema_variants,
        "log_files": file_stats,
        "totals": dict(sorted(total.items())),
        "unique_students": len(students),
        "unique_raw_skills": len(skills),
        "unique_problems": len(problems),
        "label_files": labels,
        "students_in_both_label_files": len(label_sets["training_label.csv"] & label_sets["validation_test_label.csv"]),
        "excluded_alternative_release": "anonymized_full_release_competition_dataset.csv",
        "interpretation_limits": [
            "The competition target is later STEM participation; training_label.csv is not event correctness for BKT.",
            "original identifies a non-scaffolding problem; hint identifies a hint response; attemptCount counts tutor problems attempted, not attempts on this problem.",
            "No BKT observations or train/test split are inferred from this audit.",
            "Raw skill names are not mapped to the project's Vietnamese concept/skill registry.",
            "No student IDs or row-level records are written to this report.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("docs/research/data/assistments_2017_audit.json"))
    parser.add_argument("--max-rows-per-file", type=int)
    args = parser.parse_args()
    report = audit_dataset(args.data_root, args.max_rows_per_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audited {report['totals'].get('rows', 0)} log rows; report: {args.output}")


if __name__ == "__main__":
    main()
