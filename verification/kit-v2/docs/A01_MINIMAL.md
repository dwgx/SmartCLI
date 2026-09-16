# A01_MINIMAL — 最小输入完成状态，不引入完整 actor
依据：[L1 §3，E1]；[SC2/SC4，E1]；[STD1/STD2，E1]。真实 POSIX 短写尚未验证；这是明确可注入的 OS 契约缺口，不等待实机偶然触发才补 offset。

## 1. 五种标签不是一条可以自动升级的流水线
```
accepted (0/n) → partially_written (0<k<n) → written (n/n)
                                                    ├→ app_acknowledged (有对应ACK)
                                                    └→ verified (有独立裁判)
```
accepted 后允许直接 written；空payload是明确no-op，n=0。timeout/cancel/failure是结果轴，不会把之前写出的k字节擦掉。

保留三个事实轴，而不是把后两者虚构成必经阶段：
- `write_state`: accepted / partially_written / written；及 `written_bytes,total_bytes`。
- `app_ack`: unknown / acknowledged / ignored，附 action_id/generation 与来源；不是从hash变化猜出。
- `verification`: not_run / passed / failed，附 predicate/verifier/evidence_id。

`phase` 可以作为展示摘要：verified不意味着app_ack一定存在；文件独立裁判有时能确认结果，而应用从未发ACK。不能为了展示一个最高阶段，反填所有中间事实为true。

## 2. 不改公共接口的第一增量
保留 `PtyBackend.write(data: bytes) -> None`。POSIX 内部 private `_write_all` 维护 offset，只有全部字节确认被底层调用接收才正常返回；否则抛出带 `written_bytes`、`total_bytes`、reason的 `IncompleteWrite`（兼容 OSError/RuntimeError 家族须本地决定并测试现有调用方）。库调用者不需要立即迁移。

`accepted` 对同步接口是函数已通过验证、分配了本次request上下文，不是已完成；对daemon `{ok:true}` 的旧成功响应仍必须在完整write返回后发出。禁止为了异步化提前给旧客户端ok，然后把错误藏在内部日志。

T03最小库修复只要 backend+vendor+测试。若要把 partial receipt 传到 CLI/MCP，则另一个独立增量，在不移除旧字段的前提下增加数据；字段缺失明确 unknown。当前通用error文本可做到“不说成功”，但不能声称已经给调用方完整恢复所需信息。该接口接线在未做前仍留 open。

## 3. 精确算法与边界
1. 输入固定不可变bytes，创建请求id和本session incarnation绑定（内存作用域），offset=0。
2. 调用write剩余后缀；返回n且 `0<n<=len(remaining)` 才增加offset。大于remaining是后端协议错误；0返回不算进度，进入等待或受限失败。
3. `EAGAIN/EWOULDBLOCK`：保持offset，等待可写或取消/截止；等待可虚假唤醒，继续同一后缀。不自旋，不复制全部payload重发。
4. `EINTR`：offset不变，重新检查deadline/cancel，再尝试。Python3.5+对部分被signal打断的os调用已有重试；测试注入EINTR仍可验证组合层，不表示真实系统每次都会抛它。[STD1]
5. 每次成功和失败都检查单调deadline，不让用户字节无限占owner。cancel在n字节写出后到达时报告`cancelled, written_bytes=n`，不能撤回已写字节。
6. 最后一个成功write的返回是written事实的线性化点；若它早于owner处理cancel，输出written并注明cancel太晚。若cancel先被处理，后缀不得再写。并发cancel必须有一次仲裁，不根据墙钟比较来猜。
7. `EPIPE/EIO/invalid fd` 记partial或零进度错误。会话未知/driver没有精确返回信息时`written_bytes=null`，不要填0制造可安全重试假象。

**不从 `BlockingIOError.characters_written` 推断原始 os.write 部分字节数**。Python文档说明该属性用于io buffered类；raw os.write依据返回n推进，异常路径保持已知offset。[STD2]

## 4. 哪些可延后，哪些不能
| 事项 | 现在可延后？ | 诚实边界 |
|---|---|---|
| 完整actor框架、多个排队writer | 可以 | 先单个in-flight；请求串行，partial后不得混入下一请求 |
| 跨重启持久幂等／exactly-once | 可以且两版不承诺 | 断线后无法确定结果时unknown，不自动重发整包 |
| 通用应用ACK | 可以 | app_ack永远unknown直到有真实适配 |
| 独立业务裁判 | 可以由测试/调用者提供 | 不把写完、quiet、屏幕变化宣称verified |
| 成功返回前write完整性 | 不可以 | 丢返回值仍回ok就是谎报 |
| bytes/characters单位声明 | 不可以 | Windows str API不能冒充任意原始bytes通道 |
| partial后偏移与恢复策略 | 至少错误对象必须有 | 本轮可选择暂停会话写入并让操作者决策；不得继续乱写 |
| owner公平性 | 最小库阶段可只保证deadline | 未解决同步等待阻塞时，不声称可响应所有watcher |

## 5. 与read/backpressure的相互作用
有限时write_all可避免永久阻塞，但不能独立证明全双工无死锁。一个程序可能先写满输出再读取输入，owner若一直等写而不排空读，就会直到timeout都无进度。A04接线时使用有预算的read/write轮转，或同一owner的非重入service_io；不可在write中递归执行任意新输入请求。

因此T03最小修复提供“不会假成功”，不提供“任何交互都一定继续”。这一差别写进release note，不要求本轮实现actor才能先修丢字节。

## 6. 关闭判据和NOT_RUN
至少八类单测：短写、EAGAIN、EINTR、0进度、超时、部分取消、最终字节与cancel竞争、错误后重复调用。每类都比较精确bytes和状态，不仅检查返回非异常。

本包 `models/contracts.py` 是**可执行参考模型 E2，不是生产补丁**；`tools/conformance.py --case input` 调真实PosixPtyBackend.write，但把OS写接收器替换为短写fixture，证据是E3-with-injected-OS。真实POSIX验证：一个raw-mode PTY子程序收定长payload，报告length+SHA256；限制payload和runtime、关闭其自有资源，禁止在用户普通shell里发送控制字符进行测试。

```json
{"task":"T03","unit_memory":"PASS","fault_injection":"PASS","posix_pty":"NOT_RUN","reason":"NO_POSIX_HOST_OR_NO_EXPLICIT_PTY_APPROVAL","claim":"Library fault handling only; no real PTY byte-exact claim"}
```
这允许合入明确范围的修复，不允许关闭所有平台验收或宣传全平台byte-exact。
