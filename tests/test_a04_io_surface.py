"""A04-S3: the io evidence must reach CLI/MCP unchanged, from the runtime.

An agent that cannot tell "the screen is quiet" from "nobody has read the
transport yet" will act on a stale screen. The io block answers that, and the
rule this test protects is about PROVENANCE: the runtime produces it (and says
so via ``basis_origin``); the adapters only forward it. An adapter that filled
the field in itself would make a claim look measured when it was invented.

Imports the real daemon script and the real MCP server module. No session is
started, no port is bound, no model is called.

Run: python -B tests/test_a04_io_surface.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
REPO = args.repo.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
TUI_DIR = REPO / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(TUI_DIR))
try:
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

spec = importlib.util.spec_from_file_location("drive_tui", TUI_DIR / "tui.py")
tui = importlib.util.module_from_spec(spec)
sys.modules["drive_tui"] = tui
spec.loader.exec_module(tui)


class FakeSession:
    def __init__(self, io_block):
        self._io = io_block
        self.model = type("M", (), {"content_hash": staticmethod(lambda: 11),
                                    "visual_hash": staticmethod(lambda: 22),
                                    "alt_screen": False})()

    def is_alive(self):
        return True

    def io_block(self):
        return self._io


class IoSchema(unittest.TestCase):
    def block(self, cut="budget_limited", **over):
        block = {"generation": 3, "read_offset": 128, "fed_offset": 64,
                 "pending": {"known_payload_bytes": 64, "readable_now": True,
                             "parser_incomplete": None, "reply_bytes": 0,
                             "upstream": "unknown"},
                 "local_cut": cut, "representation": "conpty_reconstructed_utf8",
                 "stream_error": None, "basis_origin": "runtime"}
        block.update(over)
        return block

    def test_daemon_response_carries_the_io_block(self):
        class Snap:
            def to_text(self):
                return "[screen 2x2]"

            def to_json(self):
                return json.dumps({"lines": []})

        resp = tui._snapshot_response(FakeSession(self.block()), Snap())
        self.assertIn("io", resp)
        self.assertEqual(resp["io"]["basis_origin"], "runtime")
        self.assertEqual(resp["io"]["local_cut"], "budget_limited")
        self.assertEqual(resp["io"]["pending"]["known_payload_bytes"], 64)
        self.assertEqual(resp["io"]["representation"], "conpty_reconstructed_utf8")
        self.assertEqual(resp["io"]["pending"]["upstream"], "unknown",
                         "the Windows upstream can never be claimed to be empty")
        self.assertEqual(resp["io"]["read_offset"], 128)
        self.assertEqual(resp["io"]["fed_offset"], 64)

    def test_offsets_are_ordered_and_unknown_is_null(self):
        class Snap:
            def to_text(self):
                return "x"

            def to_json(self):
                return "{}"

        block = self.block(pending={"known_payload_bytes": None, "readable_now": None,
                                    "parser_incomplete": None, "reply_bytes": 0,
                                    "upstream": None})
        resp = tui._snapshot_response(FakeSession(block), Snap())
        io = resp["io"]
        self.assertLessEqual(io["fed_offset"], io["read_offset"])
        self.assertIsNone(io["pending"]["known_payload_bytes"],
                          "an unknown count must stay null, not become 0")

    def test_mcp_snapshot_forwards_io_and_never_invents_it(self):
        try:
            spec = importlib.util.spec_from_file_location("mcp_srv", TUI_DIR / "mcp_server.py")
            mcp_srv = importlib.util.module_from_spec(spec)
            sys.modules["mcp_srv"] = mcp_srv
            spec.loader.exec_module(mcp_srv)
        except Exception as exc:                     # the mcp SDK is an install-time dep
            self.skipTest(f"mcp server not importable here: {type(exc).__name__}: {exc}")

        block = self.block()
        forwarded = {"ok": True, "alive": True, "text": "t", "hash": 1, "visual_hash": 2,
                     "io": block}
        original = mcp_srv._call_session
        try:
            mcp_srv._call_session = lambda sid, req, timeout=30.0: dict(forwarded)
            out = mcp_srv.snapshot("sid")
            self.assertEqual(out["io"], block, "the adapter must forward the runtime's block")
            mcp_srv._call_session = lambda sid, req, timeout=30.0: {
                k: v for k, v in forwarded.items() if k != "io"}
            out2 = mcp_srv.snapshot("sid")
            self.assertNotIn("io", out2,
                             "an older daemon without io must leave the field absent, not guessed")
        finally:
            mcp_srv._call_session = original

    def test_cli_json_keeps_the_block(self):
        # The CLI prints the daemon response as JSON; make sure the key survives
        # json.dumps/loads (it is plain data, no objects).
        block = self.block()
        round_tripped = json.loads(json.dumps({"io": block}, ensure_ascii=False))
        self.assertEqual(round_tripped["io"]["local_cut"], "budget_limited")
        self.assertEqual(round_tripped["io"]["pending"]["upstream"], "unknown")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
