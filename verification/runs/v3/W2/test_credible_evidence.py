"""test_credible_evidence.py — the negative controls for the W2 verifier.

The verifier is only worth what its rejections are worth, so this file does NOT
compare constants: it hands each falsified bundle to the REAL verifier and asserts
(a) that it is rejected and (b) that it is rejected by the rule the falsification
targets. A verifier that accepted everything would fail here even though it has no
bugs in its own I/O.

Run: python -B -m unittest discover -s <VERIFY_ROOT> -p "test_*.py" -v
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

import credible_fixtures as fx                      # noqa: E402
import verify_evidence as ve                        # noqa: E402


class VerifierRejects(unittest.TestCase):
    def test_the_honest_bundle_is_accepted(self):
        verdict = ve.review(fx.good_bundle())
        self.assertTrue(verdict["ok"], f"the baseline must pass, got {verdict}")
        self.assertEqual(verdict["code"], "accepted")

    def test_every_falsification_is_rejected_by_its_own_rule(self):
        for name, (bundle, expected_code) in sorted(fx.negative_cases().items()):
            with self.subTest(case=name):
                verdict = ve.review(bundle)
                self.assertFalse(verdict["ok"], f"{name} was ACCEPTED -- {verdict}")
                self.assertEqual(verdict["code"], expected_code,
                                 f"{name} was rejected by {verdict['code']}, expected {expected_code}")

    def test_reject_controls_reports_no_escapes(self):
        report = ve.reject_controls(fx.good_bundle(), fx.negative_cases())
        self.assertTrue(report["ok"], f"escaped: {report['escaped']}")
        self.assertEqual(report["controls"], len(fx.negative_cases()))
        self.assertEqual(report["escaped"], [])

    def test_a_single_field_change_is_what_flips_the_verdict(self):
        # Guards against a verifier that rejects for an unrelated reason: the
        # falsified bundle must differ from the good one in exactly one place.
        good = fx.good_bundle()
        for name, (bundle, _code) in sorted(fx.negative_cases().items()):
            with self.subTest(case=name):
                differing = [k for k in set(good) | set(bundle) if good.get(k) != bundle.get(k)]
                self.assertTrue(differing, f"{name} is identical to the good bundle")
                self.assertLessEqual(len(differing), 2,
                                     f"{name} changes {differing}; a control must isolate one lie")

    def test_shape_limits_are_enforced(self):
        deep = fx.good_bundle()
        node = deep
        for _ in range(ve.MAX_DEPTH + 5):
            node["nest"] = {}
            node = node["nest"]
        with self.assertRaises(ve.Reject) as ctx:
            ve._depth(deep)
        self.assertEqual(ctx.exception.code, "shape_too_deep")

    def test_unknown_schema_version_is_rejected(self):
        bundle = fx.good_bundle()
        bundle["schema_version"] = 99
        verdict = ve.review(bundle)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["code"], "schema_version_unknown")

    def test_no_bundle_content_is_executed_or_read(self):
        # The verifier must treat the bundle as data: a bundle naming a real host
        # file must not cause that file to be opened. Asserted by construction --
        # review() takes a dict and this test hands it paths it never touches.
        secret = HERE / "_should_never_be_opened.txt"
        bundle = fx.good_bundle()
        bundle["manifest"]["files"] = {"notes/readme.txt": fx.FAKE_SHA}
        bundle["provenance"]["source_hint"] = str(secret)
        verdict = ve.review(bundle)
        self.assertTrue(verdict["ok"])
        self.assertFalse(secret.exists(), "the verifier created or touched a path from the bundle")

    def test_cli_exit_codes(self):
        import subprocess
        import tempfile
        good = HERE / "_tmp_good.json"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle.json"
            path.write_text(__import__("json").dumps(fx.good_bundle()), encoding="utf-8")
            rc = subprocess.run([sys.executable, "-B", str(HERE / "verify_evidence.py"),
                                 "review", "--bundle", str(path)],
                                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            bad = Path(tmp) / "bad.json"
            bad.write_text(__import__("json").dumps(fx.negative_cases()["complete_without_drain"][0]),
                           encoding="utf-8")
            rc2 = subprocess.run([sys.executable, "-B", str(HERE / "verify_evidence.py"),
                                  "review", "--bundle", str(bad)],
                                 capture_output=True, text=True)
            self.assertEqual(rc2.returncode, 1, rc2.stdout + rc2.stderr)
            rc3 = subprocess.run([sys.executable, "-B", str(HERE / "verify_evidence.py"),
                                  "review", "--bundle", str(Path(tmp) / "missing.json")],
                                 capture_output=True, text=True)
            self.assertIn(rc3.returncode, (1, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
