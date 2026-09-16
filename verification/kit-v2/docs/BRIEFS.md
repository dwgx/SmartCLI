# BRIEFS — 三份可直接交给本地编码 Agent 的任务
独立全文：`../briefs/01_T05.md`、`../briefs/02_T04.md`、`../briefs/03_A04_PROTOTYPE.md`。每份首行都有worker fence；它们是任务模板，不代表网页端已经启动任何worker。

R1合入顺序：T05 → T04 → T03。第三份brief是A04原型，交的是有界模型和设计，不是生产代码；没有把T03从优先序删除。T03的最小方案在`A01_MINIMAL.md`，待相应E3逻辑与POSIX门槛决策。

## 共同不变量
所有worker保留：原Python/CLI/MCP入口、打包映射、canonical/vendor同步、有效interleave快操作、resize的legacy延后、认证、SS3与两屏行为。必须用明确边界而不是“约30行”控范围。少几行不代表正确，多几行测试不是收益膨胀。

仅一个writer进入同一树；默认在当前Agent会话直接做，不再派发其他模型。结果写到派发者已创建的RUN子目录，不在源码树塞聊天历史。缓存前缀保持不变，后续修正追加记录。

## 状态写法
```json
{"task":"T05","status":"verified_memory","changed_files":[],"old_red":{"verdict":"ASSERTION_FAILED","case":"test_real_chinese_menu"},"new_green":{"verdict":"PASS"},"bug_restored_red":{"verdict":"ASSERTION_FAILED","case":"test_real_chinese_menu"},"candidate_restored_green":{"verdict":"PASS"},"native_pty":{"status":"NOT_RUN","reason":"NOT_REQUIRED_FOR_THIS_MEMORY_INCREMENT"},"commit":"NOT_CREATED"}
```
示例是结构，不是已执行结果。T04不能只关分片测试，独立语义及超限恢复同时满足才关闭。A04纯模型永远不写`runtime_fixed=true`。
