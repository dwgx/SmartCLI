# SmartCLI — project instructions

## ⚠️ 硬性红线:严禁密集/并发 spawn 真实进程(会卡死/崩溃本机)

2026-07-13 事故:在一个会话里短时间内反复 spawn 大量真实进程(多个 grok/codex/
kiro-cli 全屏 TUI + 反复起关 daemon + mutation 来回 git checkout + verify_fx 每次
又开一堆 PTY 子进程),累积瞬时并发把用户 Windows 机器拖到卡死,用户被迫重启。
单个进程都清理干净了(零残留),元凶是**叠加的瞬时并发峰值**。

以后必须遵守:
1. **一次只驱动一个 PTY/TUI 会话。** 跑完立刻 `close` + 确认 `tui.py list` 零残留,
   再起下一个。绝不同时开多个 agent CLI(grok/codex/kiro-cli 每个都拉起
   node/rust 进程 + winpty,极吃资源)。
2. **重活(verify_fx、run_all、drive-probe 全套)先征得用户同意再跑**,且串行、
   分开跑,不在一个会话里堆几十个进程。verify_fx 每跑一次要 spawn 一大批 PTY 特效
   子进程——尤其重。
3. **mutation 验证要克制**:来回 git checkout + 重跑 PTY 探针代价高;能用代码级
   断言证明的就别反复起真实进程。
4. **看到 spawn 层错误**(`uv_spawn`、`EUNKNOWN`、exit 143/45、Git-bash spawn
   失败)= 系统在示警资源紧张,**立即停手**,别换 shell 硬上。
5. 需要用户自己跑重活时,建议用 `! python tests\verify_fx.py`(前缀 `!` 在会话里
   直接跑),而不是我又开一批子进程。

## Git commits
- 不加任何 AI 署名(遵循用户全局 CLAUDE.md)。
- 只有用户明确要求才 commit。

## 回归门(任何改动后须仍 exit 0,但按上面红线：串行、经同意、别堆并发）
详见 `NEXT-STEPS.md` 顶部与 `HANDOFF.md` §2。
