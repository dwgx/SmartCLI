#!/usr/bin/env python
"""_sandbox_fuzz_core.py — PURE-IN-MEMORY adversarial fuzz of the SmartCLI core.

⚠️ SAFETY CONTRACT (see repo CLAUDE.md red line, 2026-07-13 incident):
This sandbox spawns ZERO processes, opens ZERO sockets, does ZERO PTY work and
runs SINGLE-THREADED. It exercises only pure functions / in-memory pyte:
    bytes -> ScreenModel.feed -> build_snapshot -> to_text/to_json
    readiness.* under a virtual clock (no real sleeping)
    session._resolve_key / KEY_MAP  (string -> bytes)
    fx effects as pure frame producers  (w,h,t -> str)
It can burn CPU/tokens freely but can NEVER load the machine with concurrent
real subprocesses. The guards below hard-fail if that contract is violated.

Exit 0 = every invariant held across all fuzz iterations (robust).
Exit 1 = an invariant was violated (a real defect — printed with the seed input).

Run:  set PYTHONIOENCODING=utf-8 && python tests/_sandbox_fuzz_core.py
Determinism: a fixed master seed; every failure prints the exact input to repro.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---- SAFETY GUARD: forbid the process-spawning surface entirely ------------
# If any import below pulls in subprocess or the PtySession/daemon path, fail
# LOUDLY before running a single iteration — this is the whole point of the
# sandbox being safe to run at any scale.
_FORBIDDEN = ("subprocess", "socket", "winpty", "pty")


def _assert_no_spawn_surface() -> None:
    leaked = [m for m in _FORBIDDEN if m in sys.modules]
    # pyte/stdlib never import these; smartcli_core.session imports 'socket'?
    # No — only scripts/tui.py does. Importing screen_model/snapshot/readiness
    # and session's KEY_MAP must stay spawn-free. We check AFTER our imports.
    if leaked:
        print(f"SAFETY VIOLATION: forbidden modules imported: {leaked}")
        print("This sandbox must stay pure in-memory. Aborting.")
        raise SystemExit(2)


MASTER_SEED = 0x5A17
MAX_WALL_SECONDS = 90.0  # hard self-abort ceiling
_start = time.monotonic()


def _budget_ok() -> bool:
    return (time.monotonic() - _start) < MAX_WALL_SECONDS


# ---- imports of the PURE surface only --------------------------------------
from smartcli_core.screen_model import ScreenModel      # noqa: E402
from smartcli_core.snapshot import build_snapshot, Snapshot, _contiguous_spans  # noqa: E402
from smartcli_core import readiness                      # noqa: E402
from smartcli_core.session import KEY_MAP, _resolve_key  # noqa: E402

_assert_no_spawn_surface()  # session/screen_model/snapshot/readiness must be spawn-free


# ---- results plumbing ------------------------------------------------------
_failures: list[tuple[str, str]] = []
_iterations = 0


def _fail(section: str, detail: str) -> None:
    _failures.append((section, detail))


# =============================================================================
# SECTION 1 — perception chain fuzz: arbitrary bytes must never crash the
# bytes -> ScreenModel -> build_snapshot -> to_text/to_json pipeline, and
# to_json must ALWAYS emit valid parseable JSON.
# =============================================================================

# building blocks likely to trip an ANSI/pyte/snapshot edge
_ANSI_FRAGMENTS = [
    b"\x1b[", b"\x1b[0m", b"\x1b[31m", b"\x1b[7m", b"\x1b[1;33;44m",
    b"\x1b[999;999H", b"\x1b[2J", b"\x1b[H", b"\x1b]0;", b"\x07",
    b"\x1b[?1049h", b"\x1b[?1049l", b"\x1b[?25l", b"\x1b[?25h",
    b"\x1b[38;2;255;0;128m", b"\x1b[48;2;10;20;30m", b"\x1bOP",
    b"\r", b"\n", b"\r\n", b"\t", b"\x08", b"\x00", b"\x7f",
    b"\xff\xfe", b"\xe4\xb8", b"\xe4\xb8\xad",  # partial + full UTF-8 (中)
    b"\xf0\x9f\x98", b"\xf0\x9f\x98\x80",       # partial + full emoji
    "═╬╗│▀▁█".encode("utf-8"), "你好世界".encode("utf-8"),
    b"A" * 300, b" " * 200, b"\x1b" * 20,
]


def _rand_bytes(rng: random.Random) -> bytes:
    parts = []
    for _ in range(rng.randint(1, 40)):
        if rng.random() < 0.7:
            parts.append(rng.choice(_ANSI_FRAGMENTS))
        else:
            parts.append(bytes(rng.randint(0, 255) for _ in range(rng.randint(1, 12))))
    return b"".join(parts)


def fuzz_perception(rng: random.Random, n: int) -> None:
    global _iterations
    for _ in range(n):
        if not _budget_ok():
            return
        _iterations += 1
        cols = rng.choice([1, 2, 20, 80, 100, 200, 400])
        rows = rng.choice([1, 2, 24, 30, 50])
        data = _rand_bytes(rng)
        try:
            m = ScreenModel(cols=cols, rows=rows)
            # feed in random-sized chunks to exercise the incremental stream
            i = 0
            while i < len(data):
                step = rng.randint(1, 7)
                m.feed(data[i:i + step])
                i += step
            snap = build_snapshot(m)
            txt = snap.to_text()
            js = snap.to_json()
        except Exception as exc:  # any crash is a defect
            _fail("perception", f"CRASH {type(exc).__name__}: {exc} "
                                f"| cols={cols} rows={rows} data={data!r}")
            continue
        # invariant A: to_json is always valid JSON
        try:
            parsed = json.loads(js)
        except Exception as exc:
            _fail("perception", f"to_json not valid JSON: {exc} | data={data!r}")
            continue
        # invariant B: text/json are strings, size is echoed correctly
        if not isinstance(txt, str) or parsed.get("size") != {"rows": rows, "cols": cols}:
            _fail("perception", f"size mismatch/echo | cols={cols} rows={rows} "
                                f"got={parsed.get('size')}")
        # invariant C: every reported span sits within screen bounds
        for mi in parsed.get("regions", {}).get("menu_items", []):
            if not (0 <= mi["col_start"] <= mi["col_end"] <= cols
                    and 0 <= mi["row"] < rows):
                _fail("perception", f"span out of bounds {mi} | cols={cols} rows={rows}")
        sel = parsed.get("selected")
        if sel and not (0 <= sel["col_start"] <= sel["col_end"] <= cols
                        and 0 <= sel["row"] < rows):
            _fail("perception", f"selected out of bounds {sel} | cols={cols} rows={rows}")


# =============================================================================
# SECTION 2 — _contiguous_spans is a pure list transform; property-check it.
# =============================================================================

def fuzz_spans(rng: random.Random, n: int) -> None:
    global _iterations
    for _ in range(n):
        if not _budget_ok():
            return
        _iterations += 1
        cols = rng.sample(range(0, 50), rng.randint(0, 20))
        try:
            spans = _contiguous_spans(cols)
        except Exception as exc:
            _fail("spans", f"CRASH {type(exc).__name__}: {exc} | cols={cols}")
            continue
        # invariants: sorted, non-overlapping, end>start, cover exactly the input set
        covered = set()
        last_end = -1
        for (a, b) in spans:
            if not (a < b and a >= last_end):
                _fail("spans", f"bad span ordering {spans} | cols={sorted(cols)}")
                break
            covered.update(range(a, b))
            last_end = b
        if covered != set(cols):
            _fail("spans", f"coverage mismatch {spans} != set({sorted(cols)})")


# =============================================================================
# SECTION 3 — readiness under a virtual clock: must ALWAYS terminate within
# max_wait and only ever return the three legal reasons.
# =============================================================================

class _VClock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s if s > 0 else 0.001


def fuzz_readiness(rng: random.Random, n: int) -> None:
    global _iterations
    for _ in range(n):
        if not _budget_ok():
            return
        _iterations += 1
        clk = _VClock()
        real_mono, real_sleep = readiness.time.monotonic, readiness.time.sleep
        readiness.time.monotonic = clk.monotonic
        readiness.time.sleep = clk.sleep
        try:
            # scripted random read/hash streams
            reads = [bytes(rng.randint(0, 5)) for _ in range(rng.randint(0, 8))]
            it = iter(reads)
            hashes = [rng.randint(0, 3) for _ in range(rng.randint(1, 30))]
            hit = iter(hashes)
            last_h = [0]

            def read_fn():
                return next(it, b"")

            def hash_fn():
                last_h[0] = next(hit, last_h[0])
                return last_h[0]

            def text_fn():
                return rng.choice(["", "ready> ", "loading...", "$ "])

            def snap_fn():
                return object()

            marker = rng.choice([None, "ready", "zzz-never", "\\$"])
            max_wait = rng.choice([1, 50, 500, 2000])
            reason, _snap = readiness.wait_ready(
                read_fn, hash_fn, text_fn, snap_fn,
                marker=marker, max_wait_ms=max_wait,
                quiet_ms=rng.choice([0, 50, 200]),
                min_wait_ms=rng.choice([0, 50]),
                blank_hash=rng.choice([None, 0]),
            )
            if reason not in ("MARKER", "STABLE", "TIMEOUT"):
                _fail("readiness", f"illegal reason {reason!r}")
            if clk.t > (max_wait / 1000.0) + 1.0:  # generous grace margin
                _fail("readiness", f"exceeded max_wait: t={clk.t} max={max_wait}ms")
        except Exception as exc:
            _fail("readiness", f"CRASH {type(exc).__name__}: {exc}")
        finally:
            readiness.time.monotonic = real_mono
            readiness.time.sleep = real_sleep


# =============================================================================
# SECTION 4 — key encoding: every KEY_MAP token, C-/M-/^ combo, and arbitrary
# single chars must resolve to bytes without crashing.
# =============================================================================

def fuzz_keys(rng: random.Random, n: int) -> None:
    global _iterations
    # all named keys always resolve to their exact bytes
    for name, expected in KEY_MAP.items():
        _iterations += 1
        try:
            if _resolve_key(name) != expected:
                _fail("keys", f"KEY_MAP token {name!r} did not round-trip")
        except Exception as exc:
            _fail("keys", f"CRASH on {name!r}: {type(exc).__name__}: {exc}")
    # random combos + arbitrary unicode
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ@[]\\ "
    for _ in range(n):
        if not _budget_ok():
            return
        _iterations += 1
        kind = rng.random()
        if kind < 0.3:
            tok = "C-" + rng.choice(letters)
        elif kind < 0.5:
            tok = "^" + rng.choice(letters)
        elif kind < 0.7:
            tok = "M-" + rng.choice(letters)
        else:
            tok = chr(rng.randint(1, 0x2FFF))  # arbitrary unicode incl. CJK/box
        try:
            out = _resolve_key(tok)
            if not isinstance(out, (bytes, bytearray)):
                _fail("keys", f"{tok!r} resolved to non-bytes {type(out)}")
        except Exception as exc:
            _fail("keys", f"CRASH on {tok!r}: {type(exc).__name__}: {exc}")


# =============================================================================
# SECTION 5 — fx effects are pure frame producers; each must render random
# sizes/times/params without crashing and return a well-formed frame string.
# =============================================================================

def fuzz_fx(rng: random.Random, n: int) -> None:
    """Mirror tests/test_fx_contract.py::render — fresh instance, setup(),
    render(ctx), teardown() — but at random (w,h,t,frame_index). Pure: an
    Effect must never touch the terminal, only return a frame string."""
    global _iterations
    fx_dir = _ROOT / "skills" / "cmd-art"
    if str(fx_dir) not in sys.path:
        sys.path.insert(0, str(fx_dir))
    try:
        from fx import registry            # noqa: E402
        from fx.base import FrameCtx        # noqa: E402
        from fx.theme import get_theme      # noqa: E402
        registry.load_all()
        classes = list(registry.all_effects())
    except Exception as exc:
        _fail("fx", f"could not import/enumerate fx: {type(exc).__name__}: {exc}")
        return
    if not classes:
        _fail("fx", "no effects enumerated (registry empty?)")
        return
    for _ in range(n):
        if not _budget_ok():
            return
        _iterations += 1
        cls = rng.choice(classes)
        w = rng.choice([1, 2, 10, 40, 80, 120])
        h = rng.choice([1, 2, 5, 12, 24, 40])
        t = rng.choice([0.0, 0.1, 1.0, 5.0, 100.0])
        fi = rng.choice([0, 1, 5, 93, 1000])
        try:
            eff = cls()
            eff.setup()
            try:
                ctx = FrameCtx(t=t, frame_index=fi, width=w, height=h,
                               theme=get_theme(cls.preferred_theme),
                               params=cls.param_defaults())
                frame = eff.render(ctx)
            finally:
                try:
                    eff.teardown()
                except Exception:
                    pass
            if not isinstance(frame, str):
                _fail("fx", f"{cls.name} returned non-str frame {type(frame)}")
        except Exception as exc:
            _fail("fx", f"{cls.name} CRASH w={w} h={h} t={t} fi={fi}: "
                        f"{type(exc).__name__}: {exc}")


# =============================================================================
# runner
# =============================================================================

def main() -> int:
    rng = random.Random(MASTER_SEED)
    print("=" * 64)
    print("PURE-IN-MEMORY core fuzz sandbox (zero processes, single-thread)")
    print("=" * 64)
    sections = [
        ("perception chain (bytes->snapshot->json)", fuzz_perception, 4000),
        ("contiguous spans property", fuzz_spans, 4000),
        ("readiness virtual-clock", fuzz_readiness, 3000),
        ("key encoding", fuzz_keys, 4000),
        ("fx frame contract", fuzz_fx, 2000),
    ]
    for label, fn, count in sections:
        before = len(_failures)
        t0 = time.monotonic()
        fn(rng, count)
        dt = time.monotonic() - t0
        new = len(_failures) - before
        status = "OK  " if new == 0 else "FAIL"
        print(f"  [{status}] {label:<44} {dt:5.1f}s  (+{new} defects)")
    print("=" * 64)
    print(f"iterations: {_iterations}   defects: {len(_failures)}")
    if _failures:
        print("-" * 64)
        for section, detail in _failures[:20]:
            d = detail if len(detail) < 300 else detail[:300] + "..."
            print(f"  [{section}] {d}")
        if len(_failures) > 20:
            print(f"  ... and {len(_failures) - 20} more")
        print("RESULT: DEFECTS FOUND")
        return 1
    print("RESULT: all invariants held — core is robust under fuzz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
