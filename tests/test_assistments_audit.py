import csv
import json
import tempfile
import unittest
from pathlib import Path

from research.data.audit_assistments_2017 import audit_dataset


class AssistmentsAuditTests(unittest.TestCase):
    def test_counts_and_privacy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "training"
            logs.mkdir()
            columns = ["ITEST_id", "actionId", "skill", "problemId", "startTime", "correct", "original", "hint", "hintCount", "scaffold", "attemptCount"]
            with (logs / "student_log_1.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerow(dict(zip(columns, ["secret-student-a", "action-1", "fractions", "p1", "10", "1", "1", "0", "0", "0", "1"])))
                writer.writerow(dict(zip(columns, ["secret-student-a", "action-2", "fractions", "p1", "9", "0", "0", "secret-student-b", "1", "0", "2"])))
            for name, student in (("training_label.csv", "secret-student-a"), ("validation_test_label.csv", "secret-student-b")):
                with (logs / name).open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["ITEST_id", "MCAS"])
                    writer.writerow([student, "1"])

            report = audit_dataset(root)
            self.assertEqual(report["totals"]["rows"], 2)
            self.assertEqual(report["totals"]["time_regressions_in_file_order"], 1)
            self.assertEqual(report["log_files"][0]["field_values"]["hint"], {"0": 1, "<invalid>": 1})
            self.assertEqual(report["students_in_both_label_files"], 0)
            self.assertNotIn("secret-student", json.dumps(report))

    def test_missing_required_column_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "student_log_1.csv").write_text("ITEST_id,correct\na,1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                audit_dataset(root)


if __name__ == "__main__":
    unittest.main()
