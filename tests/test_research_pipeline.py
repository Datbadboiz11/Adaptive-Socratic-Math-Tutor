"""Synthetic edge cases only; these are regression tests, not research test data."""
import csv
import importlib.util
import itertools
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.bkt.benchmark import benchmark, evaluate, read_split
from research.bkt.metrics import metrics
from research.bkt.model import fit, likelihood_gradient, pack, step
from research.data.preprocess_assistments_2017 import COLUMNS, DEFAULT_CONFIG, preprocess, pseudonym, split_students


def event(student="s", problem="p", action="1", time="10", **kwargs):
    return {"ITEST_id": student, "problemId": problem, "actionId": action, "startTime": time,
            "skill": "fractions", "assignmentId": "assignment", "assistmentId": problem,
            "correct": "1", "original": "1", "hint": "0", "hintCount": "0",
            "scaffold": "0", "bottomHint": "0", **kwargs}


class PipelineTests(unittest.TestCase):
    def run_fixture(self, rows):
        # All artifacts live under a synthetic root; no actual student logs are used.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "data"
            training = data / "raw"
            training.mkdir(parents=True)
            with (training / "student_log_1.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
            config["expected_log_files"] = 1
            config_path = root / "protocol.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            out = data / "processed/run"
            with patch("research.data.preprocess_assistments_2017.ROOT", root):
                report = preprocess(data, out, config_path)
                with self.assertRaises(FileExistsError):
                    preprocess(data, out, config_path)
            observations = []
            for split in ("train", "dev", "test"):
                with (out / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
                    observations.extend(dict(r, split=split) for r in csv.DictReader(stream))
            return report, observations

    @staticmethod
    def control_rows():
        return [event(student=f"control-{i}", problem=f"control-{i}", action=str(100 + i), time=str(100 + i)) for i in range(20)]

    def test_first_answer_preserved_later_hint_and_retry_excluded(self):
        rows = [event(correct="0"), event(action="2", time="11", hint="1", hintCount="1"),
                event(action="3", time="12", hintCount="1"), event(action="4", time="20", assignmentId="new")]
        report, observations = self.run_fixture(rows[::-1] + self.control_rows())
        matches = [r for r in observations if r["student_id"] == pseudonym("student", "s")]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["correct"], "0")
        self.assertEqual(report["decision_counts"]["repeated_problem_exposure"], 3)
        self.assertFalse(report["test_evaluated"])
        self.assertEqual(sum(report["decision_counts"].values()), len(rows) + 20)

    def test_no_later_answer_promoted_after_hint_missing_label_or_unknown_skill(self):
        rows = [event(hint="1", hintCount="1"), event(action="2", time="11"),
                event(student="missing", correct=""), event(student="missing", action="3", time="12"),
                event(student="unknown", skill="noskill"), event(student="unknown", action="4", time="12")]
        # action IDs are globally unique; do not accidentally conflict synthetic cases.
        rows[2]["actionId"] = "5"
        rows[4]["actionId"] = "6"
        report, observations = self.run_fixture(rows + self.control_rows())
        excluded = {pseudonym("student", s) for s in ("s", "missing", "unknown")}
        self.assertTrue(all(r["student_id"] not in excluded for r in observations))
        self.assertEqual(report["decision_counts"]["hint_or_assisted"], 1)

    def test_exact_duplicate_once_conflicting_action_never_retained(self):
        same = event()
        rows = [same, same, event(student="conflict", action="7", correct="0"),
                event(student="conflict", action="7", correct="1")]
        report, observations = self.run_fixture(rows + self.control_rows())
        self.assertEqual(report["decision_counts"]["duplicate_action"], 1)
        self.assertEqual(report["decision_counts"]["conflicting_action_id"], 2)
        self.assertEqual(sum(r["student_id"] == pseudonym("student", "s") for r in observations), 1)

    def test_scaffold_parent_support_and_time_conflict(self):
        rows = [event(problem="child", action="1", original="0", scaffold="1", assistmentId="parent"),
                event(problem="parent", action="2", time="11", assistmentId="parent"),
                event(student="time", action="3", time="11"), event(student="time", action="4", time="10")]
        report, observations = self.run_fixture(rows + self.control_rows())
        self.assertEqual(report["decision_counts"]["prior_parent_support_or_unknown"], 1)
        self.assertEqual(report["decision_counts"]["ambiguous_exposure_order"], 1)
        self.assertTrue(all(r["student_id"] not in {pseudonym("student", "s"), pseudonym("student", "time")} for r in observations))

    def test_split_is_disjoint_reproducible_and_report_redacted(self):
        rows = self.control_rows()
        rows += [event(student="control-0", problem="second", action="999", time="999")]
        report, observations = self.run_fixture(rows)
        partitions = {}
        for row in observations:
            partitions.setdefault(row["student_id"], set()).add(row["split"])
        self.assertTrue(all(len(splits) == 1 for splits in partitions.values()))
        self.assertEqual([report["split_counts"][s]["students"] for s in ("train", "dev", "test")], [14, 3, 3])
        config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(split_students(list(partitions), config), split_students(list(partitions)[::-1], config))
        self.assertNotIn("control-0", json.dumps(report))
        self.assertNotIn(pseudonym("student", "control-0"), json.dumps(report))


class MetricsTests(unittest.TestCase):
    def test_auc_ties_and_missing_class(self):
        self.assertEqual(metrics([0, 1, 0, 1], [.5] * 4)["auc"], .5)
        self.assertEqual(metrics([0, 1], [.1, .9])["auc"], 1)
        self.assertEqual(metrics([0, 1], [.9, .1])["auc"], 0)
        self.assertIsNone(metrics([1, 1], [.1, .8])["auc"])
        self.assertAlmostEqual(metrics([0, 1], [.5, .5])["log_loss"], math.log(2))
        self.assertAlmostEqual(metrics([0, 1], [.5, .5])["brier"], .25)

    def test_invalid_probabilities_and_alignment(self):
        for y, p in (([], []), ([0], []), ([2], [.2]), ([0], [float("nan")]), ([0], [1.1])):
            with self.assertRaises(ValueError):
                metrics(y, p)


class BKTTests(unittest.TestCase):
    def test_dev_predictions_do_not_use_current_answer_and_reset_each_student(self):
        params = {"prior": .2, "learn": .1, "guess": .2, "slip": .1}
        pooled = {"parameters": params}
        rows = [{"student_id": s, "skill_id": "skill", "correct": y, "order_id": i}
                for i, (s, y) in enumerate((("a", 0), ("a", 1), ("b", 1)), 1)]
        _, output = evaluate(rows, {}, pooled, {}, .5)
        changed = [dict(r) for r in rows]
        changed[0]["correct"] = 1
        _, alternative = evaluate(changed, {}, pooled, {}, .5)
        for model in ("bkt", "skill_rate", "history_rate"):
            self.assertEqual(output[0][model], alternative[0][model])
            self.assertEqual(output[0][model], output[2][model])
        self.assertNotEqual(output[1]["bkt"], alternative[1]["bkt"])
        self.assertNotEqual(output[1]["history_rate"], alternative[1]["history_rate"])

    def test_split_loader_rejects_duplicates_and_backwards_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "train.csv"
            for second in (("a", "skill", "o1", "2", "1"), ("a", "skill", "o2", "0", "1")):
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("student_id", "skill_id", "opportunity_id", "order_id", "correct"))
                    writer.writerows([("a", "skill", "o1", "1", "0"), second])
                with self.assertRaises(ValueError):
                    read_split(path)

    def test_prediction_matches_enumerated_hidden_state_paths_and_backend(self):
        from backend.app.knowledge import update
        params = {"prior": .2, "learn": .1, "guess": .2, "slip": .1}
        evidence, state = [], params["prior"]
        for observation in (1, 0, 1, 0, 1):
            joint_known = 0.0
            joint_total = 0.0
            # Independently sum probabilities over all hidden state histories.
            for states in itertools.product((0, 1), repeat=len(evidence) + 1):
                weight = params["prior"] if states[0] else 1 - params["prior"]
                for i, y in enumerate(evidence):
                    prob_correct = 1 - params["slip"] if states[i] else params["guess"]
                    weight *= prob_correct if y else 1 - prob_correct
                    weight *= (1 if states[i + 1] else 0) if states[i] else (params["learn"] if states[i + 1] else 1 - params["learn"])
                joint_total += weight
                if states[-1]:
                    joint_known += weight
            mastery = joint_known / joint_total
            prediction, after = step(state, observation, params)
            self.assertAlmostEqual(prediction, mastery * .9 + (1 - mastery) * .2, places=12)
            result = update(state, bool(observation), params)
            self.assertAlmostEqual(prediction, result["prediction_before"], places=12)
            self.assertAlmostEqual(after, result["mastery_after"], places=12)
            state = after
            evidence.append(observation)


@unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("scipy"), "Requires research/requirements.txt")
class OptimizerTests(unittest.TestCase):
    def test_benchmark_fits_train_only_and_never_opens_test(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            processed = root / "data/processed"
            processed.mkdir(parents=True)
            config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
            (processed / "protocol.json").write_text(json.dumps(config), encoding="utf-8")
            manifest = {"students": {"train-student": "train", "dev-student": "dev", "sealed-student": "test"}}
            (processed / "split_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            columns = ("student_id", "skill_id", "problem_id", "opportunity_id", "order_id", "correct")
            for split, student, correct in (("train", "train-student", 0), ("dev", "dev-student", 1)):
                with (processed / f"{split}.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(columns)
                    writer.writerows((student, "skill", f"p{i}", f"{split}-o{i}", i + 1, correct) for i in range(3))
            (processed / "test.csv").write_text("DO NOT READ THIS FILE", encoding="utf-8")
            from research.data.preprocess_assistments_2017 import digest_file
            report = {"artifact_sha256": {name: digest_file(processed / name) for name in ("train.csv", "dev.csv", "protocol.json", "split_manifest.json")}, "limitations": []}
            (processed / "preprocessing_report.json").write_text(json.dumps(report), encoding="utf-8")
            code = root / "research/bkt"
            code.mkdir(parents=True)
            for filename in ("model.py", "metrics.py"):
                (code / filename).write_text("# synthetic hash fixture\n", encoding="utf-8")
            original_open = Path.open

            def no_test_open(path, *args, **kwargs):
                if path.name == "test.csv":
                    raise AssertionError("Benchmark opened sealed test")
                return original_open(path, *args, **kwargs)

            fake_fit = {"parameters": {"prior": .2, "learn": .1, "guess": .2, "slip": .1, "forget": 0}, "starts": [], "train_log_loss": .5, "boundary_parameters": []}
            with patch("research.bkt.benchmark.ROOT", root), patch("pathlib.Path.open", no_test_open), patch("research.bkt.benchmark.fit", return_value=fake_fit) as fitting:
                result = benchmark(processed, root / "data/experiment")
            self.assertEqual(fitting.call_count, 1)
            self.assertEqual(fitting.call_args.args[0], [[0, 0, 0]])
            self.assertFalse(result["test_evaluated"])
            self.assertEqual(result["results"]["bkt"]["micro"]["positive"], 3)

    def test_gradient_matches_finite_differences(self):
        import numpy as np
        theta = np.array([.3, .08, .2, .12])
        packed = pack([[0, 1, 1, 0], [1, 1], [0], [1, 0, 0]])
        _, gradient = likelihood_gradient(theta, packed)
        for i in range(4):
            delta = np.zeros(4)
            delta[i] = 1e-6
            numeric = (likelihood_gradient(theta + delta, packed)[0] - likelihood_gradient(theta - delta, packed)[0]) / 2e-6
            self.assertAlmostEqual(gradient[i], numeric, places=7)

    def test_fit_reduces_train_loss_and_predicts_before_update(self):
        config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))["fit"]
        seqs = [[0, 0, 1, 1, 1], [1, 1, 0, 1], [0, 1, 1], [0, 0, 0], [1, 0]] * 5
        artifact = fit(seqs, config)
        initial = min(likelihood_gradient(s, pack(seqs))[0] for s in config["starts"])
        self.assertLessEqual(artifact["train_log_loss"], initial)
        self.assertLess(artifact["parameters"]["guess"], 1 - artifact["parameters"]["slip"])
        self.assertEqual(artifact["parameters"]["forget"], 0)


if __name__ == "__main__":
    unittest.main()
