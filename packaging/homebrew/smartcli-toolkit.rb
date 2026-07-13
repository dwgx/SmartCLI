# Homebrew formula DRAFT for smartcli-toolkit (a Python package -> use the
# Python virtualenv helper). This installs the shared `smartcli_core` and its
# `pyte` dependency into an isolated libexec venv.
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
# Get the sha256 values:
#   curl -L -o s.tar.gz <the url below> && shasum -a 256 s.tar.gz   # for the sdist
#   (repeat for the pyte resource url)
class SmartcliToolkit < Formula
  include Language::Python::Virtualenv

  desc "Pluggable-PTY + pyte core for driving/perceiving/rendering the terminal"
  homepage "https://github.com/dwgx/SmartCLI"
  url "https://files.pythonhosted.org/packages/source/s/smartcli-toolkit/smartcli_toolkit-0.1.2.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000" # TODO: sdist sha256
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
  end
end
