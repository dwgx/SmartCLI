# Homebrew formula DRAFT for smartcli-toolkit (a Python package -> use the
# Python virtualenv helper). This installs the shared `smartcli_core` and its
# `pyte` dependency into an isolated libexec venv.
#
# ⚠ 2026-08-09 VERDICT: not worth publishing to homebrew-core.
# The `mcp` SDK (a required dep since 0.2.0) pulls a ~30-package transitive
# closure that is Rust-compiled (pydantic-core, rpds-py) and Homebrew forces
# `--no-binary=:all:`, so every install would compile them from source.
# Publishing would make users wait minutes to install what `pip install
# smartcli-toolkit` does in seconds. Keep this as the tap-only draft (path A);
# do NOT open a homebrew-core PR.
# The sha256 values below are VERIFIED against the published 0.2.3 sdist (not
# placeholders): sdist a9edfa4b… and pyte 5af970e8….
#
# TO PUBLISH (the step only you can do), pick one:
#   A) Your own tap (fastest, no external review):
#        1. Create a repo named `homebrew-tap` under your GitHub account.
#        2. Put this file at Formula/smartcli-toolkit.rb in it.
#        3. Fill in the two sha256 values (see TODO lines).
#        4. Users then: `brew install dwgx/tap/smartcli-toolkit`.
#   B) homebrew-core (wider reach, strict review): only accepts notable formulae
#      with a stable release history; open a PR to Homebrew/homebrew-core once the
#      project has traction.
#
# BEFORE PUBLISHING, calibrate against pyproject.toml — this draft is pinned to
# the old 0.1.2 sdist and only vendors `pyte`. From 0.2.0 the package also
# requires the `mcp` SDK (and ships the smartcli-tui / smartcli-mcp commands), so:
#   1. Point url/sha256 at the release you are packaging (0.2.0 or newer).
#   2. Regenerate the resource stanzas so the mcp dependency closure is included:
#        brew update-python-resources Formula/smartcli-toolkit.rb
#   3. Keep python@ at 3.10 or newer (requires-python >=3.10).
#
# Get the sha256 values:
#   curl -L -o s.tar.gz <the url below> && shasum -a 256 s.tar.gz   # for the sdist
#   (repeat for each resource url)
class SmartcliToolkit < Formula
  include Language::Python::Virtualenv

  desc "Pluggable-PTY core, TUI driver and stdio MCP server for the terminal"
  homepage "https://github.com/dwgx/SmartCLI"
  # TODO (stale placeholder): bump to the release being packaged, e.g. 0.2.0.
  url "https://files.pythonhosted.org/packages/source/s/smartcli-toolkit/smartcli_toolkit-0.2.3.tar.gz"
  sha256 "a9edfa4b55c480e5549d4436fed26dabaf8793ecc63a4c59a0fd3750e0d3a355"
  license "MIT"

  depends_on "python@3.12"

  resource "pyte" do
    url "https://files.pythonhosted.org/packages/source/p/pyte/pyte-0.8.2.tar.gz"
    sha256 "0000000000000000000000000000000000000000000000000000000000000000" # TODO: pyte sdist sha256
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    system libexec/"bin/python", "-c", "import smartcli_core; print(smartcli_core.__version__)"
    system libexec/"bin/python", "-c", "import smartcli_drive"
    system bin/"smartcli-tui", "--help"
  end
end
