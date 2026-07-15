"""python -m smartcli_core — environment diagnostics.

Prints the OS, Python, terminal, and dependency facts that most affect how
SmartCLI behaves, so a bug report can start from ground truth instead of a
round-trip of "which OS? which terminal? is pywinpty installed?". Inspired by
`textual diagnose`, which its maintainers called the single most valuable thing
for cutting issue back-and-forth on a cross-platform, terminal-sensitive tool.

Pure/read-only: it imports nothing that spawns a process and never opens a PTY.
Run it and paste the output into an issue.
"""
from __future__ import annotations

import os
import platform
import sys


def _ver(mod_name: str, dist_name: str | None = None) -> str:
    """Best-effort version string for an optional dependency, or a clear absent
    marker. Tries the module's __version__, then importlib.metadata."""
    import importlib
    import importlib.metadata as md
    import importlib.util

    if importlib.util.find_spec(mod_name) is None:
        return "not installed"
    try:
        mod = importlib.import_module(mod_name)
        v = getattr(mod, "__version__", None)
        if v:
            return str(v)
    except Exception:
        pass
    try:
        return md.version(dist_name or mod_name)
    except Exception:
        return "installed (version unknown)"


def _section(title: str, rows: list[tuple[str, str]]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    width = max((len(k) for k, _ in rows), default=0)
    for k, v in rows:
        print(f"  {k:<{width}}  {v}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        from . import __version__ as core_version
    except Exception:
        core_version = "?"

    print("=" * 60)
    print("SmartCLI diagnostics")
    print("=" * 60)

    _section("SmartCLI", [
        ("smartcli_core", core_version),
        ("import path", os.path.dirname(os.path.abspath(__file__))),
    ])

    _section("Python & OS", [
        ("python", sys.version.split()[0]),
        ("implementation", platform.python_implementation()),
        ("executable", sys.executable),
        ("platform", platform.platform()),
        ("machine", platform.machine()),
    ])

    # Terminal facts that change SmartCLI's behavior (isatty gates keyboard
    # input; TERM/COLORTERM affect what programs emit; on Windows the PTY path
    # is ConPTY via pywinpty).
    is_win = sys.platform == "win32"
    _section("Terminal", [
        ("stdout.isatty()", str(sys.stdout.isatty())),
        ("stdin.isatty()", str(sys.stdin.isatty())),
        ("TERM", os.environ.get("TERM", "(unset)")),
        ("COLORTERM", os.environ.get("COLORTERM", "(unset)")),
        ("PYTHONIOENCODING", os.environ.get("PYTHONIOENCODING", "(unset)")),
        ("stdout.encoding", getattr(sys.stdout, "encoding", "?") or "?"),
    ])

    _section("PTY backend & deps", [
        ("default backend", "ConPTY (pywinpty)" if is_win else "POSIX pty (stdlib)"),
        ("pyte", _ver("pyte")),
        ("pywinpty", _ver("winpty", "pywinpty") if is_win else "n/a (POSIX)"),
    ])

    _section("Optional extras", [
        ("pyfiglet", _ver("pyfiglet")),
        ("Pillow (PIL)", _ver("PIL", "Pillow")),
        ("wcwidth", _ver("wcwidth")),
    ])

    # Notes that commonly explain reports.
    notes = []
    if is_win and (os.environ.get("PYTHONIOENCODING", "").lower() not in ("utf-8", "utf8")):
        notes.append("Windows without PYTHONIOENCODING=utf-8 — box/CJK glyphs may "
                     "crash on a legacy codepage. Set it before running.")
    if _ver("pyte") == "not installed":
        notes.append("pyte is REQUIRED and missing — `pip install smartcli-toolkit`.")
    if is_win and _ver("winpty", "pywinpty") == "not installed":
        notes.append("pywinpty missing on Windows — the ConPTY backend can't run.")
    if notes:
        print("\nNotes")
        print("-----")
        for n in notes:
            print(f"  ! {n}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
