"""verify_evidence.py — offline reviewer for SmartCLI evidence bundles (W2).

A bundle is a JSON document that says what a run observed, what it confirmed and
what it could not. The verifier's job is NOT to summarise it: it is to REJECT the
bundles that claim more than their own fields support. A green run of the tools is
worthless if a fabricated "complete" passes review, so every rule here is paired
with a fixture in credible_fixtures.py that must fail.

Design rules (from docs/v3/EVIDENCE_STANDARD.md and the W2 brief):
  * offline: the bundle is data. Nothing from it is imported, executed or fetched,
    and no path inside it is read -- only its shape, its own hashes and its
    internal consistency are checked.
  * raw and derived stay separate: a bundle carries the runtime's raw observation
    and any human/model summary side by side, and a conflict is a REPORTED
    conflict (provenance_conflict), never a silently chosen winner.
  * unknown is not zero: a missing count is `null`, and a claim that needs a value
    the bundle does not carry is rejected as UNSUPPORTED rather than accepted.
  * no bundle may claim more than its own evidence level allows (E3 memory results
    cannot carry a native-PTY claim, and so on).

CLI:
    python verify_evidence.py review --bundle B.json [--out report.json]
    python verify_evidence.py reject-controls --bundle GOOD.json [--out report.json]
    python verify_evidence.py explain  --bundle B.json
Exit codes: 0 = accepted, 1 = rejected, 2 = the bundle could not be read at all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA_VERSION = 2
MAX_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 24
MAX_ITEMS = 20000

EVIDENCE_LEVELS = {"E1", "E2", "E3", "E4", "E5", "E6"}
CLAIM_SCOPES = {"memory", "loopback", "native_pty", "agent_task", "release"}
CUT_VALUES = {"drained", "budget_limited", "unknown", "error"}
REPRESENTATIONS = {"posix_pty_stream", "conpty_reconstructed_utf8"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Reject(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _depth(node, level=0):
    if level > MAX_DEPTH:
        raise Reject("shape_too_deep", f"nesting deeper than {MAX_DEPTH}")
    if isinstance(node, dict):
        for v in node.values():
            _depth(v, level + 1)
    elif isinstance(node, list):
        for v in node:
            _depth(v, level + 1)


def _load(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise Reject("bundle_too_large", f"{len(raw)} bytes > {MAX_BYTES}")
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Reject("bundle_unreadable", f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(bundle, dict):
        raise Reject("bundle_not_an_object", type(bundle).__name__)
    _depth(bundle)
    return bundle


def _need(bundle: dict, *path, ) -> object:
    node: object = bundle
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise Reject("missing_field", ".".join(str(p) for p in path))
        node = node[key]
    return node


def _check_hashes(bundle: dict) -> None:
    files = bundle.get("manifest", {}).get("files")
    if files is None:
        raise Reject("missing_field", "manifest.files")
    if not isinstance(files, dict) or not files:
        raise Reject("manifest_empty", "manifest.files must be a non-empty mapping")
    if len(files) > MAX_ITEMS:
        raise Reject("manifest_too_large", str(len(files)))
    for name, digest in files.items():
        if not isinstance(name, str) or not name or name.startswith("/") or ".." in name.split("/"):
            raise Reject("path_escape", f"unsafe manifest entry {name!r}")
        if os.path.isabs(name) or re.match(r"^[A-Za-z]:", name):
            raise Reject("path_escape", f"absolute manifest entry {name!r}")
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            raise Reject("hash_malformed", f"{name}: {digest!r}")


def _check_claims(bundle: dict) -> None:
    claims = bundle.get("claims")
    if not isinstance(claims, list) or not claims:
        raise Reject("claims_missing", "claims must be a non-empty list")
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise Reject("claim_not_an_object", f"claims[{i}]")
        level = claim.get("evidence")
        if level not in EVIDENCE_LEVELS:
            raise Reject("evidence_level_unknown", f"claims[{i}].evidence={level!r}")
        scope = claim.get("scope")
        if scope not in CLAIM_SCOPES:
            raise Reject("claim_scope_unknown", f"claims[{i}].scope={scope!r}")
        # A claim may not exceed the evidence that carries it: memory work cannot
        # assert a native-transport result, and no level below E6 may claim a
        # release verification.
        if scope == "native_pty" and level in {"E1", "E2", "E3"}:
            raise Reject("claim_exceeds_evidence",
                         f"claims[{i}]: scope=native_pty with evidence={level}")
        if scope == "release" and level != "E6":
            raise Reject("claim_exceeds_evidence",
                         f"claims[{i}]: scope=release with evidence={level}")
        if claim.get("verified") is True and not claim.get("evidence_ref"):
            raise Reject("claim_without_evidence_ref", f"claims[{i}]")


def _check_observation(bundle: dict) -> None:
    obs = bundle.get("observation")
    if obs is None:
        return                                  # optional for pure harness bundles
    cut = _need(obs, "local_cut")
    if cut not in CUT_VALUES:
        raise Reject("cut_unknown", repr(cut))
    representation = _need(obs, "representation")
    if representation not in REPRESENTATIONS:
        raise Reject("representation_unknown", repr(representation))
    pending = _need(obs, "pending")
    if not isinstance(pending, dict):
        raise Reject("pending_not_an_object", type(pending).__name__)
    known = pending.get("known_payload_bytes")
    if known is not None and (not isinstance(known, int) or known < 0):
        raise Reject("pending_count_malformed", repr(known))
    # The whole point of the cut vocabulary: a NOT-drained observation may not be
    # reported as a complete one.
    if cut != "drained" and bundle.get("completion", {}).get("state") == "complete":
        raise Reject("complete_without_drain",
                     f"local_cut={cut} but completion.state=complete")
    read_off, fed_off = obs.get("read_offset"), obs.get("fed_offset")
    if isinstance(read_off, int) and isinstance(fed_off, int) and fed_off > read_off:
        raise Reject("offsets_inverted", f"fed_offset={fed_off} > read_offset={read_off}")
    if representation == "conpty_reconstructed_utf8":
        if obs.get("source_wire_exact") is True:
            raise Reject("wire_exact_claimed_on_conpty",
                         "ConPTY composes the stream; a raw-wire claim is unsupportable")
        if pending.get("upstream") != "unknown":
            raise Reject("conpty_upstream_claimed",
                         f"upstream={pending.get('upstream')!r} (must stay unknown)")


def _check_input(bundle: dict) -> None:
    inp = bundle.get("input")
    if inp is None:
        return
    planned, received = inp.get("planned_bytes"), inp.get("received_bytes")
    if not isinstance(planned, int) or planned < 0:
        raise Reject("planned_bytes_malformed", repr(planned))
    partial = inp.get("write_state") in {"accepted", "partially_written"}
    if received is None and not partial:
        raise Reject("received_bytes_missing", "a completed write must report received_bytes")
    if isinstance(received, int):
        if received > planned:
            raise Reject("received_exceeds_planned", f"{received} > {planned}")
        if received < planned and inp.get("write_state") == "written":
            raise Reject("written_but_short",
                         f"write_state=written with {received}/{planned}")
        if received < planned and inp.get("status") == "PASS":
            raise Reject("pass_with_partial_input", f"{received}/{planned} yet status=PASS")
    planned_sha, received_sha = inp.get("planned_sha256"), inp.get("received_sha256")
    for name, digest in (("planned_sha256", planned_sha), ("received_sha256", received_sha)):
        if digest is not None and not (isinstance(digest, str) and SHA256_RE.match(digest)):
            raise Reject("hash_malformed", f"input.{name}")
    if planned_sha and received_sha and planned_sha == received_sha and isinstance(received, int) \
            and isinstance(planned, int) and received != planned:
        raise Reject("hash_contradicts_length",
                     "identical sha256 for different byte counts is impossible")


def _check_cancel_and_close(bundle: dict) -> None:
    cancel = bundle.get("cancel", {})
    if cancel.get("acknowledged") is True and cancel.get("process_exited") is True \
            and not cancel.get("exit_observed_by"):
        raise Reject("cancel_claimed_as_exit",
                     "an acknowledged cancellation is not an observed process exit")
    close = bundle.get("close", {})
    if close.get("state") == "closed_confirmed" and close.get("confirmed_by") in (None, "", "assumed"):
        raise Reject("close_confirmed_without_observation",
                     "closed_confirmed requires an observed confirmation")
    if close.get("state") == "closed_confirmed" and close.get("close_unconfirmed") is True:
        raise Reject("close_state_contradiction", "closed_confirmed and close_unconfirmed together")


def _check_provenance(bundle: dict) -> None:
    """Raw and derived stand side by side; a conflict is reported, not resolved."""
    prov = bundle.get("provenance")
    if prov is None:
        raise Reject("missing_field", "provenance")
    origin = prov.get("basis_origin")
    if origin not in {"runtime", "adapter", "reviewer", "conflict"}:
        raise Reject("basis_origin_unknown", repr(origin))
    if origin == "adapter" and bundle.get("claims") and any(
            c.get("basis") == "runtime" for c in bundle["claims"]):
        raise Reject("adapter_claim_named_runtime",
                     "a claim labelled runtime must not rest on an adapter's basis")
    reported = prov.get("reported_values")
    if isinstance(reported, dict) and len(set(map(str, reported.values()))) > 1 \
            and origin != "conflict":
        raise Reject("provenance_conflict_hidden",
                     "the sources disagree; basis_origin must be 'conflict' "
                     "(or the disagreement must be resolved by a stated rule)")
    if prov.get("basis_origin") == "conflict" and not prov.get("conflict_note"):
        raise Reject("provenance_conflict_unexplained", "conflict without a note")


def _check_replay(bundle: dict) -> None:
    replay = bundle.get("replay")
    if replay is None:
        return
    if replay.get("complete") is True and replay.get("event_gaps"):
        raise Reject("replay_complete_with_gaps",
                     f"gaps={replay['event_gaps']!r} but complete=true")
    if replay.get("complete") is True and replay.get("state") != "drained":
        raise Reject("replay_complete_without_drain", f"state={replay.get('state')!r}")


def _check_selected(bundle: dict) -> None:
    """A 'selected label' claim must carry the label it actually read."""
    snap = bundle.get("snapshot")
    if not isinstance(snap, dict):
        return
    selected = snap.get("selected")
    if isinstance(selected, dict) and selected.get("text") in (None, ""):
        raise Reject("selected_text_empty",
                     "a selected-row claim without text cannot be checked against the screen")
    if isinstance(selected, dict) and selected.get("inferred") is True \
            and snap.get("claim") == "observed":
        raise Reject("inference_claimed_as_observation",
                     "an inferred selection is not an observed one")


CHECKS = (_check_hashes, _check_claims, _check_provenance, _check_observation,
          _check_input, _check_cancel_and_close, _check_replay, _check_selected)


def review(bundle: dict) -> dict:
    if bundle.get("schema_version") != SCHEMA_VERSION:
        return {"ok": False, "code": "schema_version_unknown",
                "detail": repr(bundle.get("schema_version")), "checks_run": 0}
    for i, check in enumerate(CHECKS):
        try:
            check(bundle)
        except Reject as exc:
            return {"ok": False, "code": exc.code, "detail": exc.detail, "checks_run": i + 1}
    return {"ok": True, "code": "accepted", "detail": "no rule fired", "checks_run": len(CHECKS)}


def reject_controls(good: dict, cases: dict) -> dict:
    """Run every negative fixture: each MUST be rejected, and by its own rule."""
    results = []
    baseline = review(good)
    results.append({"case": "baseline_good", "expected": "accept", **baseline})
    for name, entry in sorted(cases.items()):
        bundle, expected_code = entry if isinstance(entry, tuple) else (entry, None)
        verdict = review(bundle)
        results.append({"case": name, "expected": "reject", "expected_code": expected_code,
                        **verdict})
    escaped = [r for r in results[1:] if r["ok"]]
    wrong_rule = [r for r in results[1:] if not r["ok"] and r["code"] == "accepted"]
    return {
        "ok": bool(baseline["ok"]) and not escaped and not wrong_rule,
        "controls": len(results) - 1,
        "escaped": [r["case"] for r in escaped],
        "results": results,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["review", "reject-controls", "explain"])
    ap.add_argument("--bundle", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.bundle is None:
        print("error: --bundle is required", file=sys.stderr)
        return 2
    try:
        bundle = _load(args.bundle)
    except Reject as exc:
        payload = {"ok": False, "code": exc.code, "detail": exc.detail}
        print(json.dumps(payload, indent=1))
        return 2 if exc.code == "bundle_unreadable" else 1

    if args.command == "explain":
        verdict = review(bundle)
        print(json.dumps({"verdict": verdict}, indent=1))
        return 0 if verdict["ok"] else 1
    if args.command == "reject-controls":
        sys.path.insert(0, str(Path(__file__).parent))
        from credible_fixtures import negative_cases
        report = reject_controls(bundle, negative_cases())
        report["sha256"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
        text = json.dumps(report, indent=1)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 0 if report["ok"] else 1
    verdict = review(bundle)
    text = json.dumps(verdict, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
