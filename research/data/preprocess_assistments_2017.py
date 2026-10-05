"""Disk-backed, conservative ASSISTments action -> observation preprocessing.

Run as ``python -m research.data.preprocess_assistments_2017`` from repository root.
All row-level outputs are local under ignored data/. Existing runs are never replaced.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from functools import lru_cache
from pathlib import Path

from research.data.audit_assistments_2017 import find_training_dir

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "research/config/assistments2017.v1.json"
COLUMNS = (
    "ITEST_id", "actionId", "skill", "problemId", "assignmentId", "assistmentId",
    "startTime", "correct", "original", "hint", "hintCount", "scaffold", "bottomHint",
)
OBS_COLUMNS = ("student_id", "skill_id", "problem_id", "opportunity_id", "order_id", "correct")


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=30000)
def pseudonym(kind: str, value: str) -> str:
    # Stable linkage, NOT anonymization: small ID domains remain guessable.
    return hashlib.sha256(f"assistments2017:{kind}:{value}".encode()).hexdigest()


def natural(value: str) -> int | None:
    if not value.isascii() or not value.isdecimal():
        return None
    n = int(value)
    return n if n <= 2**63 - 1 else None


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    split = config["split"]
    ratios = [split[k] for k in ("train", "dev", "test")]
    if any(not math.isfinite(v) or not 0 < v < 1 for v in ratios) or not math.isclose(sum(ratios), 1):
        raise ValueError("Split ratios must be positive and sum to one")
    if config["test_policy"] != "sealed: benchmark command reads train and dev only":
        raise ValueError("This pipeline requires a sealed test policy")
    return config


def split_students(students: list[str], config: dict) -> dict[str, str]:
    # Exact floor allocation, deterministic hash ranking, no outcome stratification.
    seed = config["split"]["seed"]
    ranked = sorted(students, key=lambda s: (hashlib.sha256(f"{seed}:{s}".encode()).hexdigest(), s))
    train_n = int(len(ranked) * config["split"]["train"])
    dev_n = int(len(ranked) * config["split"]["dev"])
    if min(train_n, dev_n, len(ranked) - train_n - dev_n) < 1:
        raise ValueError("Need enough retained students for three nonempty splits")
    return {s: "train" if i < train_n else "dev" if i < train_n + dev_n else "test"
            for i, s in enumerate(ranked)}


def _normalized(row: dict, unknown: set[str]) -> tuple:
    values = {k: (row.get(k) or "").strip() for k in COLUMNS}
    bad = ""
    if None in row or any(row.get(k) is None for k in COLUMNS):
        bad = "malformed_row"
    elif not values["ITEST_id"] or not values["problemId"] or not values["assistmentId"] or not values["assignmentId"]:
        bad = "missing_identity_or_context"
    ts, aid = natural(values["startTime"]), natural(values["actionId"])
    if not bad and (ts is None or aid is None):
        bad = "invalid_time_or_action"
    skill = values["skill"]
    if not bad and (skill.casefold() in unknown or any(c in skill for c in (";", "~~", "|", ","))):
        bad = "missing_or_ambiguous_skill"
    flags = [int(values[k]) if values[k] in {"0", "1"} else None
             for k in ("correct", "original", "hint", "scaffold", "bottomHint")]
    hints = natural(values["hintCount"])
    if not bad and (None in flags or hints is None):
        bad = "invalid_correct_or_help_flags"
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return (
        pseudonym("student", values["ITEST_id"]) if values["ITEST_id"] else "",
        pseudonym("problem", values["problemId"]) if values["problemId"] else "",
        pseudonym("assistment", values["assistmentId"]) if values["assistmentId"] else "",
        pseudonym("skill", skill) if skill else "", ts, aid, *flags, hints, bad, fingerprint,
    )


def preprocess(data_root: Path, output: Path, config_path: Path = DEFAULT_CONFIG) -> dict:
    config = load_config(config_path)
    data_root, output = data_root.resolve(), output.resolve()
    # Do not allow local pseudonymous records to escape the ignored data tree.
    if not output.is_relative_to(ROOT / "data"):
        raise ValueError("Row-level outputs must be inside repository data/")
    training = find_training_dir(data_root)
    expected = [training / f"student_log_{i}.csv" for i in range(1, config["expected_log_files"] + 1)]
    found = set(training.glob("student_log_*.csv"))
    if found != set(expected):
        raise ValueError("Training log set differs from expected consecutive source files")
    if output == data_root or output.is_relative_to(training) or training.is_relative_to(output):
        raise ValueError("Output must be separate from the raw training directory")
    output.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(output / "staging.sqlite3")
    try:
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA cache_size=-32768")
        db.execute("""CREATE TABLE actions(
            row_id INTEGER PRIMARY KEY, source_file TEXT, source_row INTEGER,
            student TEXT, problem TEXT, assistment TEXT, skill TEXT, ts INTEGER, aid INTEGER,
            correct INTEGER, original INTEGER, hint INTEGER, scaffold INTEGER, bottom INTEGER,
            hints INTEGER, bad TEXT, fingerprint TEXT)""")
        source_manifest, skill_names = [], {}
        row_id = 0
        reference = None
        unknown = {s.casefold() for s in config["unknown_skills"]}
        for path in expected:
            count = 0
            batch = []
            before = path.stat()
            source_hash = digest_file(path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                columns = reader.fieldnames or []
                if len(columns) != len(set(columns)) or not set(COLUMNS).issubset(columns):
                    raise ValueError(f"{path.name}: missing or duplicate required headers")
                if reference is not None and [c.casefold() for c in columns] != reference:
                    raise ValueError(f"{path.name}: structural schema drift")
                reference = [c.casefold() for c in columns]
                for source_row, row in enumerate(reader, 2):
                    row_id += 1
                    count += 1
                    normalized = _normalized(row, unknown)
                    batch.append((row_id, path.name, source_row, *normalized))
                    skill = (row.get("skill") or "").strip()
                    if skill:
                        skill_names[pseudonym("skill", skill)] = skill
                    if len(batch) == 5000:
                        db.executemany("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                        batch.clear()
                if batch:
                    db.executemany("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError(f"{path.name}: source changed while preprocessing")
            source_manifest.append({"file": path.name, "rows": count, "bytes": before.st_size, "sha256": source_hash})
            db.commit()
            print(f"Staged {path.name}: {count} actions", flush=True)
        db.execute("CREATE INDEX action_ids ON actions(aid)")
        db.execute("CREATE INDEX problem_history ON actions(student,problem,ts,aid,row_id)")
        db.execute("CREATE INDEX parent_history ON actions(student,assistment,ts,aid)")
        db.executescript("""
            CREATE TABLE conflicts AS SELECT aid FROM actions WHERE aid IS NOT NULL
                GROUP BY aid HAVING COUNT(DISTINCT fingerprint)>1;
            CREATE UNIQUE INDEX conflicting_ids ON conflicts(aid);
            CREATE TABLE dedup AS SELECT aid, MIN(row_id) AS first_row FROM actions
                WHERE aid IS NOT NULL GROUP BY aid;
            CREATE UNIQUE INDEX dedup_ids ON dedup(aid);
            CREATE TABLE ranked AS SELECT row_id,
                ROW_NUMBER() OVER(PARTITION BY student,problem ORDER BY ts,aid,row_id) AS rank
                FROM actions;
        """)
        # Include invalid/conflicting earlier actions in exposure ranking: never promote
        # a later answer because the earlier answer was missing, assisted, or corrupted.
        db.execute("""CREATE TABLE decisions AS SELECT a.row_id,
            CASE
              WHEN a.bad!='' THEN a.bad
              WHEN c.aid IS NOT NULL THEN 'conflicting_action_id'
              WHEN a.row_id!=d.first_row THEN 'duplicate_action'
              WHEN r.rank!=1 THEN 'repeated_problem_exposure'
              WHEN a.original!=1 OR a.scaffold!=0 THEN 'non_original_or_scaffold'
              WHEN a.hint!=0 OR a.hints!=0 OR a.bottom!=0 THEN 'hint_or_assisted'
              WHEN EXISTS(SELECT 1 FROM actions p WHERE p.student=a.student AND p.problem=a.problem
                   AND p.aid<a.aid AND (p.ts>a.ts OR p.ts IS NULL)) THEN 'ambiguous_exposure_order'
              WHEN EXISTS(SELECT 1 FROM actions p WHERE p.student=a.student AND p.assistment=a.assistment
                   AND (p.ts IS NULL OR p.ts<a.ts OR (p.ts=a.ts AND p.aid<a.aid))
                   AND (p.hint=1 OR p.scaffold=1 OR p.original=0 OR p.bad!='')) THEN 'prior_parent_support_or_unknown'
              ELSE 'retained_first_original_no_recorded_help'
            END AS reason
            FROM actions a JOIN ranked r ON a.row_id=r.row_id
            LEFT JOIN conflicts c ON a.aid=c.aid LEFT JOIN dedup d ON a.aid=d.aid""")
        db.execute("CREATE INDEX decision_rows ON decisions(row_id)")
        retained = "retained_first_original_no_recorded_help"
        students = [r[0] for r in db.execute("SELECT DISTINCT a.student FROM actions a JOIN decisions d USING(row_id) WHERE d.reason=?", (retained,))]
        assignment = split_students(students, config)
        db.execute("CREATE TABLE splits(student TEXT PRIMARY KEY, split TEXT)")
        db.executemany("INSERT INTO splits VALUES (?,?)", assignment.items())
        split_counts = {}
        for split in ("train", "dev", "test"):
            counts = Counter()
            skills, split_students_set = set(), set()
            with (output / f"{split}.csv").open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(OBS_COLUMNS)
                query = """SELECT a.student,a.skill,a.problem,a.ts,a.aid,a.correct FROM actions a
                    JOIN decisions d USING(row_id) JOIN splits s ON a.student=s.student
                    WHERE d.reason=? AND s.split=? ORDER BY a.student,a.ts,a.aid,a.row_id"""
                for student, skill, problem, ts, aid, correct in db.execute(query, (retained, split)):
                    opportunity = pseudonym("opportunity", student + ":" + problem)
                    counts["observations"] += 1
                    counts["correct"] += correct
                    split_students_set.add(student)
                    skills.add(skill)
                    # Sequence order is monotonically increasing within each student.
                    writer.writerow((student, skill, problem, opportunity, counts["observations"], correct))
            split_counts[split] = {**counts, "students": len(split_students_set), "skills": len(skills)}
            if not counts["observations"]:
                raise ValueError(f"Empty {split} split")
        with (output / "decisions.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("source_file", "source_row", "reason"))
            writer.writerows(db.execute("SELECT a.source_file,a.source_row,d.reason FROM actions a JOIN decisions d USING(row_id) ORDER BY a.row_id"))
        (output / "split_manifest.json").write_text(json.dumps({"protocol_version": config["protocol_version"], "split": config["split"], "students": assignment}, indent=2) + "\n", encoding="utf-8")
        (output / "skill_manifest.json").write_text(json.dumps(skill_names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "protocol.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        reasons = dict(db.execute("SELECT reason,COUNT(*) FROM decisions GROUP BY reason ORDER BY reason"))
        hashes = {name: digest_file(output / name) for name in ("train.csv", "dev.csv", "test.csv", "split_manifest.json", "protocol.json")}
        report = {"protocol_version": config["protocol_version"], "config_sha256": digest_file(config_path),
                  "source_files": source_manifest, "input_actions": row_id, "decision_counts": reasons,
                  "split": config["split"], "split_counts": split_counts, "artifact_sha256": hashes,
                  "test_evaluated": False, "raw_to_vietnamese_mapping": "not performed",
                  "limitations": ["First recorded exposure may not be first lifetime exposure; unrecorded help is unknown.",
                                 "One observation per student/problem: repeated assignments intentionally excluded.",
                                 "No misconception labels, latent mastery ground truth, or Vietnamese calibration.",
                                 "Source skill tags are retained independently, including geometry for this public-data benchmark.",
                                 "Student split does not hold out problem families; family grouping requires content metadata.",
                                 "Pseudonyms are linkable hashes, not anonymization. Row-level artifacts remain local."]}
        assert sum(reasons.values()) == row_id
        assert sum(v["observations"] for v in split_counts.values()) == reasons[retained]
        (output / "preprocessing_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        db.commit()
        return report
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/assistments2017-v1")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    report = preprocess(args.data_root, args.output, args.config)
    print(json.dumps({"input_actions": report["input_actions"], "split_counts": report["split_counts"]}, indent=2))


if __name__ == "__main__":
    main()
