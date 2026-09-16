"""Delivery completeness checks. Historical test reports are not executed here."""
from pathlib import Path
import hashlib
import json
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

class HandoffDataTests(unittest.TestCase):
    def test_seven_requested_deliverables_exist(self):
        for name in ["ORDER", "A04_DESIGN", "A01_MINIMAL", "CONFORMANCE", "POSITIONING", "BRIEFS", "RISKS"]:
            self.assertGreater((ROOT / "docs" / (name + ".md")).stat().st_size, 800)

    def test_three_nonrecursive_worker_briefs(self):
        paths = sorted((ROOT / "briefs").glob("*.md")); self.assertEqual(len(paths), 3)
        for p in paths:
            text = p.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("YOU ARE THE WORKER. DO NOT SPAWN."))
            self.assertIn("Do not commit", text)

    def test_risk_inventory_and_scopes(self):
        data = json.loads((ROOT / "data/risks.json").read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data["risks"]
        self.assertEqual(len(rows), 18)
        self.assertEqual(len({r["id"] for r in rows}), 18)
        for r in rows:
            for field in ["trigger", "mitigation", "kill_criteria", "max_touch", "evidence"]:
                self.assertTrue(r[field])
        scopes = json.loads((ROOT / "data/scopes.json").read_text(encoding="utf-8"))
        self.assertEqual(scopes["T05"]["max_changed_files"], 3)
        self.assertEqual(scopes["T04"]["max_changed_files"], 3)
        self.assertEqual(scopes["T03"]["max_changed_files"], 3)
        self.assertEqual(scopes["A04-P"]["max_changed_files"], 0)

    def test_source_map_resolves_every_attached_snapshot(self):
        data = json.loads((ROOT / "data/source_map.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["files"]), 10)
        base = ROOT / "evidence/incoming/astra6-attachments/source-at-701e61f"
        for filename in data["files"]: self.assertTrue((base / filename).is_file())

    def test_original_v1_manifest_remains_valid(self):
        with zipfile.ZipFile(ROOT / "reference/v1_original.zip") as z:
            name = next(n for n in z.namelist() if n.endswith("/MANIFEST.json"))
            manifest = json.loads(z.read(name)); prefix = name.rsplit("/", 1)[0] + "/"
            self.assertEqual(len(manifest["files"]), 49)
            for path, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(z.read(prefix + path)).hexdigest(), digest, path)

    def test_local_evidence_preserved_and_disagreements_explicit(self):
        evidence = (ROOT / "evidence/incoming/astra6-attachments/smartcli-local-evidence-2026-09-16.md").read_text(encoding="utf-8")
        self.assertIn("selected.text='3'", evidence)
        self.assertIn("31/40", evidence)
        dissent = (ROOT / "docs/REVIEW_DISAGREEMENTS.md").read_text(encoding="utf-8")
        self.assertIn("我反对本地结论的地方", dissent)
        self.assertIn("77.5%", dissent)
        self.assertIn("E4", dissent)

if __name__ == "__main__": unittest.main()
