"""smartcli_bootstrap.py — make drive-tui self-configuring on drop-in.

The drive-tui skill depends on the ``smartcli_core`` package and the ``pyte``
(and, on Windows, ``pywinpty``) libraries. To honour "unzip, drop the folder
into the AI's skills directory, and it just works", this module locates
``smartcli_core`` no matter where the skill ended up, and verifies the runtime
deps — offering, but never silently performing, an install.

Discovery order for ``smartcli_core`` (first hit wins):
  1. ``$SMARTCLI_ROOT``                        — explicit override
  2. walk up parents of this file for a dir containing
     ``smartcli_core/__init__.py``            — running inside the repo
  3. the bundled ``_vendor/`` next to the skill — standalone / plugin drop-in
  4. already importable (pip-installed)        — nothing to do

The vendored copy in (3) is kept byte-identical to the canonical package by
``tools/sync_vendor.py`` + ``tests/test_vendor_sync.py``, so the drop-in path is
never a stale fork.

Dependency policy (safety): a missing pip dependency is a NETWORK action to fix,
so this module prints the exact install command and only installs when the
caller explicitly opts in (``ensure_deps(auto_install=True)``, or the
environment variable ``SMARTCLI_AUTO_INSTALL=1``). It never pip-installs behind
the user's back.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# scripts/ -> drive-tui/ ; the skill root holds _vendor/
_SKILL_ROOT = _HERE.parents[1]
_VENDOR = _SKILL_ROOT / "_vendor"


def _has_core(path: Path) -> bool:
    return (path / "smartcli_core" / "__init__.py").is_file()


def locate_core() -> str | None:
    """Return a sys.path entry that makes ``smartcli_core`` importable, or None
    if it is already importable without help. Prepends the found dir to
    sys.path as a side effect. Raises ImportError if it truly cannot be found."""
    # 1) explicit override
    env_root = os.environ.get("SMARTCLI_ROOT")
    if env_root and _has_core(Path(env_root)):
        _prepend(env_root)
        return env_root

    # 2) walk up from this file (covers running inside the repo checkout)
    for parent in _HERE.parents:
        if _has_core(parent):
            _prepend(str(parent))
            return str(parent)

    # 3) bundled vendor copy (standalone skill / plugin drop-in)
    if _has_core(_VENDOR):
        _prepend(str(_VENDOR))
        return str(_VENDOR)

    # 4) already installed?
    if importlib.util.find_spec("smartcli_core") is not None:
        return None

    raise ImportError(
        "smartcli_core not found. Looked at $SMARTCLI_ROOT, every parent of "
        f"{_HERE}, the bundled {_VENDOR}, and installed packages. Either keep "
        "the drive-tui folder's _vendor/ intact, set SMARTCLI_ROOT to the repo, "
        "or `pip install smartcli-toolkit`."
    )


def _prepend(path: str) -> None:
    if path and path not in sys.path:
        sys.path.insert(0, path)


# --- dependency checking ----------------------------------------------------

def _missing_deps() -> list[str]:
    missing = []
    if importlib.util.find_spec("pyte") is None:
        missing.append("pyte")
    if sys.platform == "win32" and importlib.util.find_spec("winpty") is None:
        # the pip distribution is 'pywinpty'; the import name is 'winpty'
        missing.append("pywinpty")
    return missing


def _install_cmd(pkgs: list[str]) -> str:
    return f"{sys.executable} -m pip install " + " ".join(pkgs)


def ensure_deps(auto_install: bool | None = None) -> list[str]:
    """Check runtime deps. Returns the list still missing after any install.

    ``auto_install`` None (default) -> honour ``SMARTCLI_AUTO_INSTALL`` env.
    When install is NOT opted into, prints the exact command and returns the
    missing list without touching the network.
    """
    missing = _missing_deps()
    if not missing:
        return []

    if auto_install is None:
        auto_install = os.environ.get("SMARTCLI_AUTO_INSTALL", "").strip() in ("1", "true", "yes")

    cmd = _install_cmd(missing)
    if not auto_install:
        print(f"[smartcli] missing dependency: {', '.join(missing)}", file=sys.stderr)
        print(f"[smartcli] install with:\n    {cmd}", file=sys.stderr)
        print("[smartcli] or re-run with --install-deps / SMARTCLI_AUTO_INSTALL=1 "
              "to install now.", file=sys.stderr)
        return missing

    print(f"[smartcli] installing missing dependency: {', '.join(missing)}", file=sys.stderr)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"[smartcli] auto-install failed ({exc}); run manually:\n    {cmd}",
              file=sys.stderr)
        return missing
    return _missing_deps()


def bootstrap(auto_install: bool | None = None) -> None:
    """Locate smartcli_core and verify deps. Call once at CLI startup."""
    locate_core()
    ensure_deps(auto_install=auto_install)
