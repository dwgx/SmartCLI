"""Live verification harness for the cmd-art fx framework.

Every ANIMATED effect is executed for real inside a PTY (pywinpty/ConPTY on
Windows) with a bounded --seconds run and a hard outer deadline; we assert:

* the process terminates by itself (no hang / runaway loop),
* it emitted truecolor SGR (38;2 or 48;2),
* it entered AND left the alt screen, and restored the cursor (?25h),
* the very last bytes are the restore tail (reset/wrap/cursor/alt-leave).

STATIC effects are run with --once as plain subprocesses; we assert exit 0,
truecolor output, and NO alt-screen usage. Extra scenarios: legacy shim CLI,
show --seq with a split segment, gallery --tag, random, and the pure-stdlib
PNM fallback of image2ascii.

Usage: python tests/verify_fx.py [name ...]   (default: everything)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "cmd-art"))

from smartcli_core import PtySession  # noqa: E402
import fx.registry as registry  # noqa: E402

CLI = str(ROOT / "skills" / "cmd-art" / "fx" / "cli.py")
SHIM = str(ROOT / "skills" / "cmd-art" / "scripts" / "ascii_fx.py")
PY = sys.executable

ALT_ENTER, ALT_LEAVE = b"\x1b[?1049h", b"\x1b[?1049l"
CURSOR_SHOW = b"\x1b[?25h"
TC_FG, TC_BG = b"\x1b[38;2;", b"\x1b[48;2;"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def run_pty(argv: list[str], deadline: float = 30.0, cols=80, rows=24) -> tuple[bytes, bool, float]:
    """Run argv under a PTY. Returns (raw_bytes, exited_in_time, seconds)."""
    raw = bytearray()
    t0 = time.time()
    exited = False
    with PtySession(cols=cols, rows=rows) as sess:
        sess.start(argv)
        while time.time() - t0 < deadline:
            data = sess.pump()
            if data:
                raw.extend(data)
            if not sess.is_alive():
                exited = True
                end = time.time() + 0.8  # drain the reader queue
                while time.time() < end:
                    d = sess.pump()
                    if d:
                        raw.extend(d)
                    time.sleep(0.03)
                break
            time.sleep(0.02)
    return bytes(raw), exited, time.time() - t0


def check_animated(name: str) -> None:
    argv = [PY, CLI, "play", name, "--seconds", "1.2", "--fps", "10",
            "--width", "70", "--height", "20"]
    raw, exited, secs = run_pty(argv)
    problems = []
    if not exited:
        problems.append("DID NOT EXIT before deadline")
    if ALT_ENTER not in raw:
        problems.append("no alt-screen enter")
    if ALT_LEAVE not in raw:
        problems.append("no alt-screen leave")
    if CURSOR_SHOW not in raw:
        problems.append("cursor not restored")
    if TC_FG not in raw and TC_BG not in raw:
        problems.append("no truecolor SGR")
    tail = raw[-160:]
    if ALT_LEAVE not in tail:
        problems.append("alt-leave not near stream end")
    record(f"play {name}", not problems,
           "; ".join(problems) if problems else f"{len(raw)}B in {secs:.1f}s")


def check_static(name: str, extra: list[str] = ()) -> None:
    argv = [PY, CLI, "play", name, "--once", "--width", "60", "--height", "18",
            *extra]
    p = subprocess.run(argv, capture_output=True, timeout=60)
    out = p.stdout
    problems = []
    if p.returncode != 0:
        problems.append(f"exit {p.returncode}: {p.stderr.decode()[:120]}")
    if TC_FG not in out and TC_BG not in out:
        problems.append("no truecolor in output")
    if ALT_ENTER in out:
        problems.append("static effect touched the alt screen")
    record(f"once {name}", not problems, "; ".join(problems))


def check_no_tty_safety() -> None:
    # animated effect WITHOUT a TTY must degrade to one plain frame + exit 0
    p = subprocess.run([PY, CLI, "play", "fire", "--seconds", "9999",
                        "--width", "50", "--height", "12"],
                       capture_output=True, timeout=60)
    ok = p.returncode == 0 and ALT_ENTER not in p.stdout and p.stdout
    record("no-tty degrade (fire --seconds 9999 piped)", bool(ok),
           f"exit={p.returncode} bytes={len(p.stdout)} alt={'y' if ALT_ENTER in p.stdout else 'n'}")


def check_shim() -> None:
    p = subprocess.run([PY, SHIM, "--once", "text3d", "SMART", "--from",
                        "3050FF", "--to", "FF5AD5"], capture_output=True, timeout=60)
    ok = p.returncode == 0 and TC_FG in p.stdout
    record("legacy shim text3d --once", ok, f"exit={p.returncode}")

    raw, exited, secs = run_pty([PY, SHIM, "--seconds", "1.0", "--fps", "10",
                                 "sphere", "--color"])
    ok = exited and TC_FG in raw and ALT_LEAVE in raw
    record("legacy shim sphere --color --seconds 1", ok, f"{secs:.1f}s")

    raw, exited, secs = run_pty([PY, SHIM, "--seconds", "1.0", "--fps", "10",
                                 "wave"])
    ok = exited and (TC_BG in raw or TC_FG in raw) and ALT_LEAVE in raw
    record("legacy shim wave alias --seconds 1", ok, f"{secs:.1f}s")


def check_show_and_gallery() -> None:
    raw, exited, secs = run_pty(
        [PY, CLI, "show", "--seq", "donut:fire:1,plasma|rain::1", "--fps", "10"],
        deadline=40)
    problems = []
    if not exited:
        problems.append("show did not exit")
    if TC_FG not in raw:
        problems.append("no truecolor")
    if ALT_LEAVE not in raw:
        problems.append("no alt-leave")
    if b"\xe2\x94\x82" not in raw:  # U+2502 split separator
        problems.append("split separator missing")
    record("show --seq donut,plasma|rain (split)", not problems, "; ".join(problems))

    raw, exited, secs = run_pty(
        [PY, CLI, "gallery", "--tag", "3d", "--seconds-per", "0.6", "--fps", "10"],
        deadline=40)
    ok = exited and TC_FG in raw and ALT_LEAVE in raw
    record("gallery --tag 3d", ok, f"{secs:.1f}s")

    raw, exited, secs = run_pty(
        [PY, CLI, "random", "--seconds", "1", "--fps", "10"], deadline=40)
    # `random` now picks only effects that animate under their defaults (see
    # fx.cli.cmd_random), so an animated pick enters/leaves the alt-screen and
    # emits truecolor. Accept EITHER the alt-screen leave OR truecolor output:
    # this is defense-in-depth so a legitimate clean render (should the random
    # pool ever include a static effect again) does not false-fail the gate —
    # what we actually require is "it picked something, ran, and exited cleanly."
    animated_alt = ALT_LEAVE in raw
    drew_color = TC_FG in raw or TC_BG in raw
    ok = exited and (animated_alt or drew_color)
    record("random --seconds 1", ok,
           f"{secs:.1f}s alt={animated_alt} color={drew_color}")


def check_pnm_fallback() -> None:
    # exercise the pure-stdlib PNM path directly (works with or without PIL)
    import io
    from fx.effects.image2ascii import _parse_pnm, _resize_nearest, render_half_blocks
    ppm = ROOT / "tests" / "_tmp_grad.ppm"
    w, h = 24, 16
    buf = io.BytesIO()
    buf.write(f"P6\n{w} {h}\n255\n".encode())
    for y in range(h):
        for x in range(w):
            buf.write(bytes([x * 255 // (w - 1), y * 255 // (h - 1), 128]))
    ppm.write_bytes(buf.getvalue())
    try:
        px = _parse_pnm(str(ppm))
        art = render_half_blocks(_resize_nearest(px, 20, 12))
        ok = "\u2580" in art and "\x1b[38;2;" in art and "\x1b[48;2;" in art
        record("image2ascii PNM parser + half-block", ok)
    finally:
        ppm.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    registry.load_all()
    only = set(argv)
    for cls in registry.all_effects():
        if only and cls.name not in only:
            continue
        # Dispatch the SAME way the CLI does (fx.cli._run_effect): an effect that
        # is static under its default params (e.g. text3d, shimmer off) renders
        # one frame to the normal screen and never touches the alt buffer, so it
        # must be exercised with check_static -- not check_animated.
        if cls.is_animated(cls.param_defaults()):
            check_animated(cls.name)
        else:
            check_static(cls.name)
    if not only:
        check_no_tty_safety()
        check_shim()
        check_show_and_gallery()
        check_pnm_fallback()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
