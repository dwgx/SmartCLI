# Terminal-Bench (measure ground truth)

**Statement:** Success is judged by real system state via executed test scripts, never by the agent's self-report.

**Detail / real params:** Terminal-Bench (Stanford × Laude Institute). Each task = an English instruction + a verification **test script** + an oracle solution. Pass/fail is decided by executing the tests inside an isolated Docker sandbox. ~100 tasks; run with `tb run`. The discipline: ground truth is measured, not claimed.

**Source:** https://github.com/laude-institute/terminal-bench and https://terminal-bench.ai

**See also:** [[react]], [[aci-thesis]], [[tmux-capture-pane]]
