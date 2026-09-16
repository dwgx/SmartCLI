#!/usr/bin/env python3
"""Small real-core memory contract runner. No PTY, sockets, install or network.

Repository Python is executable, not sandboxed. Explicit review consent required.
Each case is isolated in a bounded child; missing dependencies are NOT_RUN.
"""
from __future__ import annotations
import argparse
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import select
import subprocess
import sys
import threading
import time
from unittest.mock import patch

CASES = ("screen", "sgr", "input", "wait", "reject")
ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 256 * 1024


def fingerprint(repo: Path) -> dict:
    return {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((repo / "smartcli_core").glob("*.py"))}


def terminal_state(model) -> tuple:
    return (
        tuple(tuple(tuple(model.screen.buffer[y][x]) for x in range(model.cols))
              for y in range(model.rows)),
        model.cursor, model.cursor_hidden, model.title, model.alt_screen, model.app_cursor,
    )


def run_case(repo: Path, case: str) -> dict:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    from smartcli_core.screen_model import ScreenModel
    from smartcli_core.snapshot import build_snapshot
    from smartcli_core import readiness
    from smartcli_core.pty_backend import PosixPtyBackend
    import smartcli_core
    imported = Path(smartcli_core.__file__).resolve()
    if not imported.is_relative_to((repo / "smartcli_core").resolve()):
        raise RuntimeError("import resolved to the wrong installed package")
    result = {"case": case, "evidence": "E3-memory", "native_pty": "NOT_RUN",
              "module_path": str(imported), "rerun": False}
    if case == "screen":
        m = ScreenModel(cols=40, rows=5)
        m.feed("  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n".encode())
        snap = build_snapshot(m)
        actual = snap.selected.text if snap.selected else None
        expected = "保存"
        result.update(status="PASS" if actual == expected else "FAIL", expected=expected, actual=actual,
                      span=None if not snap.selected else [snap.selected.row, snap.selected.col_start, snap.selected.col_end])
    elif case == "sgr":
        vectors = [b"\x1b[4:3mX", b"\x1b[38:2::255:0:128mX", b"\x1b[48:2::0:255:0mX",
                   b"\x1b[58:2::1:2:3mX", b"\x1b[31mX", b"\x1b[2;5HX",
                   "\x1b]0;标题\x07中文".encode()]
        mismatches = []
        cuts = 0
        for payload in vectors:
            ref = ScreenModel(cols=30, rows=3); ref.feed(payload)
            wanted = terminal_state(ref)
            partitions = [[payload[:cut], payload[cut:]] for cut in range(1, len(payload))]
            partitions.append([payload[i:i+1] for i in range(len(payload))])
            rng = random.Random(1701)
            for _ in range(3):
                chunks, i = [], 0
                while i < len(payload):
                    n = rng.randint(1, 5); chunks.append(payload[i:i+n]); i += n
                partitions.append(chunks)
            for chunks in partitions:
                cuts += 1
                m = ScreenModel(cols=30, rows=3)
                for chunk in chunks: m.feed(chunk)
                if terminal_state(m) != wanted and len(mismatches) < 8:
                    mismatches.append({"kind": "partition", "payload_hex": payload.hex(),
                                       "chunk_sizes": list(map(len, chunks)), "feed_errors": m.feed_errors})
        semantic = ScreenModel(cols=10, rows=2)
        semantic.feed(b"\x1b[38:2::255:0:128mX\x1b[0m\x1b[4:3mY")
        x, y = semantic.screen.buffer[0][0], semantic.screen.buffer[0][1]
        attrs_ok = x.fg == "ff0080" and bool(y.underscore) and not bool(y.italics)
        if not attrs_ok:
            mismatches.append({"kind": "independent_semantics", "fg": x.fg,
                               "underline": y.underscore, "italic": y.italics})
        result.update(status="FAIL" if mismatches else "PASS", partitions=cuts, vectors=len(vectors),
                      mismatches=mismatches, semantic_oracle="RGB ff0080; underline true; italic false")
    elif case == "input":
        payload = "A中\x00B\r\n保存".encode("utf-8")
        sink = bytearray(); calls = 0; waits = 0
        schedule = [2, "again", "intr", 1]
        fd = 987654
        def writer(actual_fd, data):
            nonlocal calls
            if actual_fd != fd: raise OSError(errno.EBADF, "fixture refuses unrelated fd")
            calls += 1
            if calls > 32: raise RuntimeError("write-attempt budget exceeded")
            action = schedule[calls - 1] if calls <= len(schedule) else len(data)
            if action == "again": raise BlockingIOError(errno.EAGAIN, "injected")
            if action == "intr": raise InterruptedError(errno.EINTR, "injected")
            n = min(int(action), len(data)); sink.extend(bytes(data[:n])); return n
        def writable(reads, writes, errors, timeout=None):
            nonlocal waits
            waits += 1
            if waits > 32: raise RuntimeError("writable-wait budget exceeded")
            if any(f != fd for f in [*reads, *writes, *errors]):
                raise RuntimeError("unexpected descriptor")
            return [], list(writes), []
        backend = PosixPtyBackend(); backend._fd = fd
        error = None
        try:
            with patch.object(os, "write", writer), patch.object(select, "select", writable):
                backend.write(payload)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            backend._fd = None
        result.update(status="PASS" if bytes(sink) == payload and error is None else "FAIL",
                      io_mode="injected_os", planned_bytes=len(payload), received_bytes=len(sink),
                      planned_sha256=hashlib.sha256(payload).hexdigest(),
                      received_sha256=hashlib.sha256(sink).hexdigest(), calls=calls, waits=waits, error=error,
                      scope="Production method, simulated short OS writes; not native transport")
    elif case == "wait":
        reason, snap = readiness.wait_ready(read_fn=lambda: b"", get_screen_hash_fn=lambda: 1,
                    get_text_fn=lambda: "READY", get_snapshot_fn=lambda: {"text": "READY"},
                    marker="READY", min_wait_ms=0, max_wait_ms=100, poll_ms=1)
        result.update(status="PASS" if reason == "MARKER" else "FAIL", reason=reason,
                      basis="rendered_text_regex" if reason == "MARKER" else "unknown",
                      basis_origin="conformance_adapter", claim_scope="state_matches_only")
    elif case == "reject":
        m = ScreenModel(cols=12, rows=2); m.feed(b"\x1b[7m3\x1b[0m")
        matched, _ = readiness.wait_for_regex(read_fn=lambda: b"", get_text_fn=m.text,
                    get_snapshot_fn=lambda: build_snapshot(m), pattern="保存", timeout_ms=5, poll_ms=1)
        result.update(status="PASS" if matched is False else "FAIL", expected="保存", actual="3",
                      matched=bool(matched), negative_control="REJECTED" if not matched else "WRONGLY_ACCEPTED")
    return result


def run_bounded(argv: list[str], timeout: float) -> dict:
    """Bound output while reading both pipes. Only our own child can be killed."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    lock = threading.Lock(); over = threading.Event()
    def drain(name, pipe):
        while True:
            data = pipe.read(4096)
            if not data: break
            with lock:
                left = MAX_OUTPUT - sum(len(v) for v in chunks.values())
                chunks[name].extend(data[:max(0, left)])
                if len(data) > left: over.set()
            if over.is_set():
                try: proc.kill()
                except OSError: pass
                break
    threads = [threading.Thread(target=drain, args=(name, pipe), daemon=True)
               for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr))]
    for thread in threads: thread.start()
    timed_out = False
    try: proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True; proc.kill(); proc.wait(timeout=3)
    for thread in threads: thread.join(timeout=2)
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None: pipe.close()
    return {"returncode": proc.returncode, "timed_out": timed_out, "output_limited": over.is_set(),
            **{k: bytes(v).decode("utf-8", "replace") for k,v in chunks.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--case", choices=(*CASES, "all"), default="all")
    ap.add_argument("--consent-execute-reviewed-code", action="store_true")
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.consent_execute_reviewed_code:
        ap.error("review repository code, then explicitly grant execution consent")
    if not 0 < args.timeout <= 30:
        ap.error("timeout must be in (0,30]")
    repo = args.repo.resolve()
    if not (repo / "smartcli_core" / "screen_model.py").is_file():
        ap.error("repo does not contain the expected core")
    if args.out:
        out = args.out.absolute()
        if out.exists() or out.is_symlink() or not out.parent.is_dir():
            ap.error("out must be new, with an existing parent")
        resolved = out.resolve()
        if resolved.is_relative_to(repo) or resolved.is_relative_to(ROOT):
            ap.error("out must be outside repo and delivery package")
    if args.child:
        if args.case == "all": ap.error("child requires one case")
        try: result = run_case(repo, args.case)
        except ModuleNotFoundError as exc:
            result = {"case": args.case, "status": "NOT_RUN", "reason": "MISSING_DEPENDENCY", "detail": str(exc)}
        except Exception as exc:
            result = {"case": args.case, "status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "PASS" else 1 if result["status"] == "FAIL" else 2
    selected = CASES if args.case == "all" else (args.case,)
    records = []
    for case in selected:
        run = run_bounded([sys.executable, "-B", str(Path(__file__).resolve()), "--repo", str(repo),
                           "--case", case, "--child", "--consent-execute-reviewed-code"], args.timeout)
        if run["timed_out"] or run["output_limited"]:
            result = {"case": case, "status": "ERROR", "reason": "TIMEOUT_OR_OUTPUT_LIMIT"}
        else:
            try: result = json.loads(run["stdout"].strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                result = {"case": case, "status": "ERROR", "reason": "INVALID_CHILD_REPORT"}
        if (not isinstance(result, dict) or result.get("case") != case
                or result.get("status") not in {"PASS", "FAIL", "NOT_RUN", "ERROR"}):
            result = {"case": case, "status": "ERROR", "reason": "INVALID_CASE_SCHEMA"}
        result["first_exit_code"] = run["returncode"]
        expected_rc = 0 if result.get("status") == "PASS" else 1 if result.get("status") == "FAIL" else 2
        if run["returncode"] != expected_rc:
            result.update(status="ERROR", reason="EXIT_STATUS_DISAGREES_WITH_REPORT")
        result["stderr"] = run["stderr"]
        records.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    states = [r.get("status") for r in records]
    rc = 2 if any(s in {"NOT_RUN", "ERROR"} for s in states) else 1 if "FAIL" in states else 0
    try: pyte_version = importlib.metadata.version("pyte")
    except importlib.metadata.PackageNotFoundError: pyte_version = None
    try:
        head_proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, timeout=3)
        repo_head = head_proc.stdout.strip() if head_proc.returncode == 0 else "UNKNOWN"
    except (OSError, subprocess.SubprocessError):
        repo_head = "UNKNOWN"
    report = {"schema_version": 2, "repo_head": repo_head, "profile": "C0-memory", "selected_cases": list(selected),
              "python": sys.version, "pyte": pyte_version, "repo": str(repo), "source_files": fingerprint(repo),
              "native_pty": "NOT_RUN", "records": records, "rerun": False, "exit_code": rc,
              "all_selected_pass": rc == 0}
    if args.out:
        with args.out.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2); handle.write("\n")
    print(json.dumps({"summary": {k:v for k,v in report.items() if k not in {"records", "source_files"}}}, ensure_ascii=False))
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
