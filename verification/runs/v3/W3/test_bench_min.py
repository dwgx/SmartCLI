"""W3 offline: the judge must reject fabricated completions before any model budget is spent.

No process, no PTY, no network, no model: the fixture state is a plain dict and the
verdict must attribute each rejection to the claim it contradicts.

Run: python -B -m unittest discover -s W3 -p "test_bench_min.py"
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge as J  # noqa: E402


class JudgeRejects(unittest.TestCase):
    def test_honest_result_passes(self):
        verdict = J.judge(J.good_result(), {"file_lines": 3, "contains": "third line from an agent"},
                          J.plan())
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["counts_as"], "pass")

    def test_every_fabrication_is_rejected_by_its_own_rule(self):
        for name, (result, state, plan, expected) in sorted(J.negative_cases().items()):
            with self.subTest(case=name):
                verdict = J.judge(result, state, plan)
                self.assertFalse(verdict["ok"], f"{name} was ACCEPTED: {verdict}")
                self.assertEqual(verdict["code"], expected, verdict)

    def test_selftest_reports_no_escapes(self):
        report = J.judge_selftest()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["controls"], len(J.negative_cases()))
        self.assertEqual(report["escaped"], [])

    def test_an_honest_failure_is_not_a_rejection(self):
        # "the agent did not finish" must be counted as a FAILURE, not as a
        # fabricated result: rejecting it would hide real task failures.
        result = J.good_result(claimed_complete=False)
        verdict = J.judge(result, {"file_lines": 2, "contains": "second line"}, J.plan())
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["counts_as"], "failure")

    def test_hybrid_track_is_not_a_ui_claim(self):
        hybrid = J.good_result(track="H", actions=["keys", "read_file", "write_file"])
        verdict = J.judge(hybrid, {"file_lines": 3, "contains": "third line from an agent"},
                          J.plan(track="H"))
        self.assertTrue(verdict["ok"])
        self.assertNotIn("U", verdict["counts_as"], "a hybrid result must not be reported as a UI pass")

    def test_plan_validation_refuses_without_a_spend_cap(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({"task": "B1_edit_in_editor", "track": "U", "seed": 7,
                                        "model_id": "fixture-model-v1"}), encoding="utf-8")
            rc = J.main(["validate", "--plan", str(path)])
            self.assertEqual(rc, 1, "a plan without a spend cap must not validate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
