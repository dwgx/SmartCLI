"""credible_fixtures.py — one honest bundle, and one bundle per way of lying.

Every negative case is a copy of `good_bundle()` with exactly ONE falsification,
so a rejection can be attributed to that falsification rather than to a missing
field somewhere else. Each is paired with the rule code that must fire, and
test_credible_evidence.py asserts both the rejection AND the code.
"""
from __future__ import annotations

import copy
import hashlib

FAKE_SHA = hashlib.sha256(b"fixture").hexdigest()
OTHER_SHA = hashlib.sha256(b"fixture-2").hexdigest()


def good_bundle() -> dict:
    """A bundle that claims exactly what its own fields support."""
    return {
        "schema_version": 2,
        "task": "A04-S3",
        "run_id": "n1-posix-shipped-2026-09-16",
        "manifest": {"files": {"tests/test_a04_daemon_service.py": FAKE_SHA,
                               "reports/n1.json": OTHER_SHA}},
        "provenance": {
            "basis_origin": "runtime",
            "reported_values": {"waits": "32", "waits_alt": "32"},
        },
        "observation": {
            "local_cut": "drained",
            "representation": "posix_pty_stream",
            "read_offset": 262144,
            "fed_offset": 262144,
            "pending": {"known_payload_bytes": 0, "readable_now": False,
                        "parser_incomplete": False, "reply_bytes": 0,
                        "reply_error": None, "upstream": None},
            "source_wire_exact": True,
        },
        "completion": {"state": "complete", "basis": "child_exit_observed"},
        "input": {"planned_bytes": 262144, "received_bytes": 262144,
                  "planned_sha256": FAKE_SHA, "received_sha256": FAKE_SHA,
                  "write_state": "written", "status": "PASS"},
        "claims": [{"evidence": "E4", "scope": "native_pty", "verified": True,
                    "evidence_ref": "reports/n1.json", "basis": "runtime"}],
        "snapshot": {"selected": {"text": "保存", "inferred": False}, "claim": "observed"},
        "close": {"state": "closed_confirmed", "confirmed_by": "child_exit_observed",
                  "close_unconfirmed": False},
    }


def negative_cases() -> dict:
    """name -> (bundle, rule code that must fire)."""
    cases: dict[str, tuple[dict, str]] = {}

    def case(name: str, code: str, mutate) -> None:
        bundle = good_bundle()
        mutate(bundle)
        cases[name] = (bundle, code)

    # 1. metadata hash wrong
    case("metadata_hash_malformed", "hash_malformed",
         lambda b: b["manifest"]["files"].__setitem__("tests/test_a04_daemon_service.py", "deadbeef"))

    # 2. extra/missing files
    case("manifest_extra_or_missing", "manifest_empty",
         lambda b: b["manifest"].__setitem__("files", {}))

    # 3. path escape
    case("path_escape_absolute", "path_escape",
         lambda b: b["manifest"]["files"].__setitem__("C:/Windows/system32/config", FAKE_SHA))
    case("path_escape_relative", "path_escape",
         lambda b: b["manifest"]["files"].__setitem__("../secrets.txt", FAKE_SHA))

    # 4. run mismatch: a claim pointing at a run that is not this bundle's
    case("claim_without_evidence_ref", "claim_without_evidence_ref",
         lambda b: b["claims"][0].pop("evidence_ref"))

    # 5. fake selected value
    case("selected_text_empty", "selected_text_empty",
         lambda b: b["snapshot"]["selected"].__setitem__("text", ""))

    # 6. input length/hash contradiction
    case("hash_contradicts_length", "hash_contradicts_length",
         lambda b: b["input"].update({"received_bytes": 1,
                                      "received_sha256": b["input"]["planned_sha256"],
                                      # keep every OTHER field consistent with a
                                      # short write, so only the hash/length
                                      # contradiction is left to catch
                                      "write_state": "partially_written", "status": "FAIL"}))

    # 7. partial yet claims written
    case("written_but_short", "written_but_short",
         lambda b: b["input"].update({"received_bytes": 3, "write_state": "written"}))

    # 8. budget_limited yet claims complete
    case("complete_without_drain", "complete_without_drain",
         lambda b: b["observation"].__setitem__("local_cut", "budget_limited"))

    # 9. adapter basis passed off as runtime
    case("adapter_claim_named_runtime", "adapter_claim_named_runtime",
         lambda b: b["provenance"].__setitem__("basis_origin", "adapter"))

    # 9b. a hidden conflict between sources
    case("provenance_conflict_hidden", "provenance_conflict_hidden",
         lambda b: b["provenance"].__setitem__("reported_values", {"waits": "32", "waits_alt": "35"}))

    # 10. cancel acknowledged, claimed as an observed exit
    case("cancel_claimed_as_exit", "cancel_claimed_as_exit",
         lambda b: b.__setitem__("cancel", {"acknowledged": True, "process_exited": True}))

    # 11. close_unconfirmed claimed as closed
    case("close_confirmed_without_observation", "close_confirmed_without_observation",
         lambda b: b["close"].update({"state": "closed_confirmed", "confirmed_by": "assumed"}))

    # 12. event gap yet claims a complete replay
    case("replay_complete_with_gaps", "replay_complete_with_gaps",
         lambda b: b.__setitem__("replay", {"complete": True, "state": "drained",
                                            "event_gaps": [[10, 12]]}))

    # 13. a claim that exceeds its evidence (memory work claiming a native result)
    case("claim_exceeds_evidence", "claim_exceeds_evidence",
         lambda b: b["claims"][0].__setitem__("evidence", "E3"))

    # 14. ConPTY claiming raw-wire exactness
    case("wire_exact_claimed_on_conpty", "wire_exact_claimed_on_conpty",
         lambda b: b["observation"].update({"representation": "conpty_reconstructed_utf8",
                                            "source_wire_exact": True}))

    return cases


def expected_codes() -> dict:
    return {name: code for name, (_bundle, code) in negative_cases().items()}
