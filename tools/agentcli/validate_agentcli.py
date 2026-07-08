"""Validate SmartCLI control over agent-like CLIs.

The harness has two layers:

1. Local synthetic scenarios that require no API key and exercise SmartCLI skill
   calls directly: classify/explain plus recipe drive methods.
2. Optional external CLI help probes for installed open-source agent CLIs.

All interactive scenarios run through a real PTY. Screenshots are pyte/PIL
renders of the terminal state, not real tmux captures.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent
OUT_DEFAULT = THIS_DIR / "out"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "drive-tui"))
sys.path.insert(0, str(ROOT / "tools" / "screenshot"))

from smartcli_core import PtySession  # noqa: E402
from patterns import classify, explain, get, load_all  # noqa: E402
from patterns.recipes.repl_session import run_line  # noqa: E402
import shot  # noqa: E402


def _cmd(name: str, *args: str) -> List[str]:
    """Return a PTY-friendly command for an executable on this platform."""
    if os.name == "nt":
        return ["cmd.exe", "/c", name, *args]
    return [name, *args]


EXTERNAL_TARGETS = {
    "codex": {
        "command": _cmd("codex", "--help"),
        "must_contain": ["Codex CLI", "Usage:"],
        "source": "https://github.com/openai/codex",
    },
    "aider": {
        "command": _cmd("aider", "--help"),
        "must_contain": ["usage", "aider"],
        "source": "https://github.com/Aider-AI/aider",
    },
    "opencode": {
        "command": _cmd("opencode", "--help"),
        "must_contain": ["usage", "opencode"],
        "source": "https://github.com/anomalyco/opencode",
    },
    "goose": {
        "command": _cmd("goose", "--help"),
        "must_contain": ["usage", "goose"],
        "source": "https://github.com/aaif-goose/goose",
    },
}


def _write_png(sess: PtySession, out_dir: Path, name: str) -> Optional[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    shot.screen_to_png(sess.model.screen, str(path), cell_w=9, cell_h=19)
    return str(path)


def _write_png_from_bytes(data: bytes, cols: int, rows: int, out_dir: Path, name: str) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    screen = shot.render_bytes_to_screen(data, cols, rows)
    path = out_dir / f"{name}.png"
    shot.screen_to_png(screen, str(path), cell_w=9, cell_h=19)
    return str(path)


def _visible_text(sess: PtySession) -> str:
    return sess.snapshot().to_text()


def _top_pattern(sess: PtySession) -> str:
    ranked = classify(sess.snapshot())
    return ranked[0][0].name if ranked else "(none)"


def _scenario_result(name: str, ok: bool, detail: str, **data) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        **data,
    }


def scenario_repl(out_dir: Path, screenshots: bool) -> dict:
    load_all()
    sess = PtySession(cols=80, rows=24)
    try:
        sess.start([sys.executable, "-q"])
        matched, _ = sess.wait_for(r">>> ", timeout_ms=15000)
        if not matched:
            return _scenario_result("repl", False, "Python REPL prompt not seen")
        before = explain(sess.snapshot())
        res = run_line(sess, "6*7", expect=r"42")
        png = _write_png(sess, out_dir, "repl") if screenshots else None
        output = res.data.get("output")
        return _scenario_result(
            "repl",
            res.ok and output == ["42"],
            res.detail,
            top_pattern=_top_pattern(sess),
            output=output,
            explain=before,
            png=png,
        )
    finally:
        sess.close()


def scenario_confirm(out_dir: Path, screenshots: bool) -> dict:
    sess = PtySession(cols=80, rows=24)
    try:
        sess.start([sys.executable, str(THIS_DIR / "mock_agent_cli.py"), "confirm"])
        matched, _ = sess.wait_for(r"Allow tool action\?", timeout_ms=5000)
        if not matched:
            return _scenario_result("confirm", False, "confirmation prompt not seen")
        top = _top_pattern(sess)
        res = get("confirm").drive(sess, intent=True)
        text = _visible_text(sess)
        png = _write_png(sess, out_dir, "confirm") if screenshots else None
        return _scenario_result(
            "confirm",
            res.ok and "APPROVED" in text,
            res.detail,
            top_pattern=top,
            png=png,
        )
    finally:
        sess.close()


def scenario_progress(out_dir: Path, screenshots: bool) -> dict:
    sess = PtySession(cols=80, rows=24)
    try:
        sess.start([sys.executable, str(THIS_DIR / "mock_agent_cli.py"), "progress"])
        sess.wait_for(r"Processing|DONE", timeout_ms=5000)
        top = _top_pattern(sess)
        res = get("progress").drive(sess, intent=r"DONE", max_wait_ms=10000)
        text = _visible_text(sess)
        png = _write_png(sess, out_dir, "progress") if screenshots else None
        return _scenario_result(
            "progress",
            res.ok and "DONE" in text,
            res.detail,
            top_pattern=top,
            png=png,
        )
    finally:
        sess.close()


def scenario_menu(out_dir: Path, screenshots: bool) -> dict:
    if os.name != "nt":
        return _scenario_result("menu_select", True, "skipped: Windows-only msvcrt fixture")
    sess = PtySession(cols=80, rows=24)
    try:
        sess.start([sys.executable, str(ROOT / "tests" / "_menu_app.py")])
        sess.wait_for(r"Pick a fruit", timeout_ms=5000)
        top = _top_pattern(sess)
        res = get("menu_select").drive(sess, intent="Cherry")
        text = _visible_text(sess)
        png = _write_png(sess, out_dir, "menu_select") if screenshots else None
        return _scenario_result(
            "menu_select",
            res.ok and "CHOSE: Cherry" in text,
            res.detail,
            top_pattern=top,
            png=png,
        )
    finally:
        sess.close()


def scenario_search(out_dir: Path, screenshots: bool) -> dict:
    if os.name != "nt":
        return _scenario_result("search_filter", True, "skipped: Windows-only msvcrt fixture")
    sess = PtySession(cols=80, rows=24)
    try:
        sess.start([sys.executable, str(ROOT / "tests" / "_filter_app.py")])
        sess.wait_for(r"> ", timeout_ms=5000)
        top = _top_pattern(sess)
        res = get("search_filter").drive(sess, intent="grape", stop_at=1, accept=True)
        text = _visible_text(sess)
        png = _write_png(sess, out_dir, "search_filter") if screenshots else None
        return _scenario_result(
            "search_filter",
            res.ok and "PICKED: grape" in text,
            res.detail,
            top_pattern=top,
            png=png,
        )
    finally:
        sess.close()


def scenario_subagents(out_dir: Path, screenshots: bool) -> dict:
    sess = PtySession(cols=100, rows=24)
    try:
        sess.start([sys.executable, str(THIS_DIR / "mock_agent_cli.py"), "subagents"])
        matched, _ = sess.wait_for(r"ALL SUBAGENTS DONE", timeout_ms=10000)
        text = _visible_text(sess)
        png = _write_png(sess, out_dir, "subagents") if screenshots else None
        completed = sum(1 for line in text.splitlines() if "completed" in line)
        return _scenario_result(
            "subagents",
            matched and completed >= 3,
            f"observed {completed} completed worker lines",
            top_pattern=_top_pattern(sess),
            png=png,
        )
    finally:
        sess.close()


SCENARIOS: List[Callable[[Path, bool], dict]] = [
    scenario_repl,
    scenario_confirm,
    scenario_progress,
    scenario_menu,
    scenario_search,
    scenario_subagents,
]


def external_help_probe(out_dir: Path, screenshots: bool) -> List[dict]:
    results = []
    for name, spec in EXTERNAL_TARGETS.items():
        exe = spec["command"][2] if os.name == "nt" else spec["command"][0]
        installed = shutil.which(exe) is not None
        if not installed:
            results.append({
                "name": name,
                "ok": True,
                "skipped": True,
                "detail": f"{exe} not installed",
                "source": spec["source"],
            })
            continue
        data = shot.capture_cmd(spec["command"], cols=100, rows=30, seconds=6.0)
        text = data.decode("utf-8", "replace")
        ok = all(token.lower() in text.lower() for token in spec["must_contain"])
        png = _write_png_from_bytes(data, 100, 30, out_dir, f"external_{name}") if screenshots else None
        results.append({
            "name": name,
            "ok": ok,
            "skipped": False,
            "detail": "help output matched" if ok else "help output missing expected text",
            "command": spec["command"],
            "source": spec["source"],
            "png": png,
        })
    return results


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate SmartCLI control over agent-like CLIs")
    p.add_argument("--out", default=str(OUT_DEFAULT), help="output directory")
    p.add_argument("--external", action="store_true", help="also probe installed external agent CLIs")
    p.add_argument("--no-screenshots", action="store_true", help="skip PNG output")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out)
    shot_dir = out_dir / "screens"
    screenshots = not args.no_screenshots
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    scenario_results = [fn(shot_dir, screenshots) for fn in SCENARIOS]
    external_results = external_help_probe(shot_dir, screenshots) if args.external else []

    ok = all(r.get("ok") for r in scenario_results + external_results)
    report = {
        "ok": ok,
        "started": started,
        "cwd": str(ROOT),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "render_label": shot.RENDER_LABEL,
        "scenarios": scenario_results,
        "external": external_results,
    }
    report_path = out_dir / "agentcli_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"AGENTCLI validation: {'PASS' if ok else 'FAIL'}")
    for group, rows in (("scenario", scenario_results), ("external", external_results)):
        for row in rows:
            status = "SKIP" if row.get("skipped") else ("PASS" if row.get("ok") else "FAIL")
            print(f"{group:8} {row['name']:<14} {status:4} {row['detail']}")
    print(f"report: {report_path}")
    if screenshots:
        print(f"screens: {shot_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
