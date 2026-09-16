# A04_PRODUCTION — 在既有运行时上落地有界持续服务

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 0. 本文只改变 A04 的生产路线

【我的推断／设计】目标不是“加一个 owner”，而是让现有 owner 在无人查询、长等待和持续输出下仍推进**已经到达本运行时的流**，同时能说明自己没有处理完什么。T05、T04、T03 已完成部分保持关闭；本轮不重新证明它们，不把 HEAD 701e61f 的远端旧文件覆盖到未提交的本地实现。当前实施基线必须是“HEAD + 三项实现文件指纹 + 现有工作树差异”。[^L00][^L05][^L04][^L03]

【证据支持·E1】现有 `PtySession.pump()` 已经执行 read→feed→`drain_replies()`→write；设备应答写失败被吞掉。daemon 的 `INTERLEAVE_OK` 在长 wait 的 poll gap 服务快请求，且刻意不处理 resize。生产方案不能重复调用一次 `drain_replies` 以为是新机制，也不能增加另一个线程修改屏幕。[^S17][^LCD]

## 1. 对 A04P_PROPOSAL 三切片的裁决

| 提案 | 判定 | 必须修正后才能实施 |
|---|---|---|
| A：读预算 kwarg + pump + pending | 【我的推断／设计】方向正确，但不是“加可选参数就完全兼容” | 自定义 backend 可能只实现零参数 `read_nonblocking()`；`pump(max_bytes=None)` 不能无条件向它传新 kwarg；先定义预算能力和 pending 语义，不能以 unbounded read 后切片假装有限读 |
| B：仅 `queue.Empty` 时 service | 【我的推断／设计】是必要增量，但不足以覆盖服务饥饿 | requests 一直不空时也要安排 I/O；长 wait 直接调用的 pump 必须受同一预算；不能只修 idle 分支后宣布持续推进与公平性 |
| C：Windows 有界 buffer | 【我的推断／设计】应做，但须与关闭、残留片段和 generation 绑定 | 只限制队列项数不够；reader 的当前 str、编码 bytes、拒收尾部都要计入；full buffer 时不能阻断 close/EOF 控制状态；不能声称给子进程施加了已验证背压 |
| A/B/C 合并“7文件” | 【证据支持·E1，算术检查】原列举不成立 | canonical 2 + vendor 2 + daemon 1 + tests 3 + run_all 1 = 9；不是 7。设计 delta 的另一份清单是不同拆法，不能混算 |
| “每片可独立回滚” | 【我的推断／设计】有依赖条件 | B 依赖 A 的预算与 pending；回滚预算却留下 B，或回滚关闭却留下 C，会破坏契约。按切片依赖逆序撤回；不要 reset 现有工作树 |

【证据支持·E1】上表评审对象是附件提案 §2–5，不是三项已完成修复的否定。A04 原型本身仍是 E2；原型通过不能替代当前 daemon 的 E3/E4。[^LP][^LPD][^LPL]

## 2. 四个预算层，不能只选其中一个

| 层／现有符号 | 解决的真实失败 | 本轮设计契约 | 不覆盖的部分 |
|---|---|---|---|
| Windows reader：`WinptyBackend._read_loop` | 【证据支持·E4】无人轮询时积压增长 | 【我的推断／设计】既有 reader 保留；按**交付 str 的 UTF-8 再编码负载**计量容量，带 item cap、每次 spawn 独立状态和 stop-aware 等待 | 上游 ConPTY 的合成、投递延迟及 native 内部分配 |
| POSIX：`PosixPtyBackend.read_nonblocking` | 【证据支持·E4】无人读 master 时子进程阻塞 | 【我的推断／设计】每次只读取 min(剩余本轮预算, 单次读取预算)，并给出 readable / EOF / read_error 的区别 | 未经调度的 owner 无法靠更大读取上限自己运行 |
| session：`PtySession.pump` | 【证据支持·E1/E4】请求时一次吞掉积压；query reply 同步写 | 【我的推断／设计】记录本轮读入/交给 parser/保留尾部/待发 reply；不让其他观察者直接消费 transport；预算需覆盖 reply 工作 | 一次 `feed`、write、正则或 `sendall` 不可被 Python 时钟检查强制抢占 |
| daemon：`_serve_forever.worker` / `_drain_interleavable` | 【证据支持·E1】idle 不服务；快请求可无限占 poll gap | 【我的推断／设计】每次有限 I/O、有限 jobs、有限扫描；有 backlog 时继续有限轮，无 backlog 时保留阻塞等待 | A05 的接入额度、A06 的慢回包，以及尚未完成的写操作可使总时延更大 |

【证据支持·E4】失败依据来自 X2/X3；表中任何容量和调度选择都不是新增测量。[^LX2][^LX3]

【我的推断／设计】参数先用符号表达：`B_read` 单次 read 上限，`B_turn` 单轮输入处理上限，`B_reply` 应答保留上限，`B_queue` Windows 队列有效负载上限，`N_items` 项数上限，`J_fast` 每轮执行快请求上限，`J_scan` 每轮扫描队列上限，`T_soft` 轮次检查点时限。测试可取小数值穷举；生产默认值需提案和本地测量。不得把已有 0.93 s 当新实现的性能门槛，也不将 271307 B 反推为应该配置的队列大小。

【我的推断／设计】12 288 B 是该 fixture/主机的已观察阻塞点，不是 `B_turn` 的数学下限。较小读量、较频繁服务一样可能推进；大于 12 KiB 的预算若 owner 不运行也无济于事。有限源的正确性检验应覆盖比观察阻塞点小的读片，以防实现错误地依赖“一次读光”。这不要求重跑 X3 基线。[^LX3]

【证据支持·E4；我的推断】X3的fixture说明先写完512KiB，再发送CPR查询；无pump的分支停在12288字节。因此保留其“未完成、CPR=false”的观测，但该字段不能单独证明查询已经发出后被挂起。有pump分支确实证明512KiB完成并收到正确CPR。N1新增候选测试将一次query放在大输出之前，分别锁住查询应答与持续消费，不重跑历史X3。[^LX3]

### 2.1 防止“队列有界，队列外无界”

【我的推断／设计】Windows 至少公布以下记账边界：
`queued_payload_bytes`（已计入的队列）、`reader_held_payload_bytes`（未入队的 suffix）、`consumer_held_bytes`（已取出待喂 parser）、`parser_buffered_bytes`（可见的局部缓存）、`pending_reply_bytes`。给 queue 释放额度时，只能对已经转移出其所有权的区间释放一次；consumer 所持有的 bytes 仍属于 session 预算。

【我的推断／设计】若 reader 一次请求固定字符数 K，可为再编码建立单块 UTF-8 负载上界；但 native 返回 str 的实现边界、Python 对象 overhead 和 native 内部存储不能靠 `len(encoded)` 证明 RSS 有界。先读一整块再检查 cap，会产生至少一个临时块；receipt 必须分别报告 queue cap 和包含 held chunk 的总可控 payload 上界，不能报“总内存 ≤ queue cap”。假进程若违约返回超大块，应 fail-closed 并保留诊断，不截断后继续声称精确。

【我的推断／设计】EOF / stop / read_error / generation 使用旁路状态，不以 `None` 塞入可能已经满的数据队列。空块不创建无限个 queue items。每个旧 reader 捕获自己的 proc、buffer、stop token 和 generation；不得在迟到回调中重新读取 `self._queue` 后污染下一次 spawn。[^LCB]

## 3. 预算能力与 backward compatibility

【我的推断／设计】推荐先在两个内置 backend 上加入私有 `_read_budgeted(max_bytes)` / `_read_status()`，与现有无参数 `read_nonblocking()` 并存；session 的内部预算策略默认关闭。或者提交增加 optional kwarg 的方案，但必须先批准其公共扩展含义。两种方法二选一，不能都做成新 API 家族。

【我的推断／设计】无预算路径继续调用旧零参数接口。开启 budget 时，自定义 backend 若未声明实现预算能力，必须在**调用前**拒绝或保持该 session 不进入新服务 profile；不得先调用 unbounded read、吞下全部数据再切成小段，并称其有界。不要用捕获所有 `TypeError` 然后重试来探测签名：它会吞掉后端内部真实错误，还可能重复读取。

【未确认】附件没有所有下游第三方 `PtyBackend` 子类清单；新增回归须包含一个仅实现原 ABC 的最小自定义后端，以及一个在内部主动抛 TypeError 的后端。前者原调用不变，后者错误不得被掩盖。这是兼容测试，不是要求重新测已完成修复。

## 4. pending：至少区分五种事实

【我的推断／设计】下面是待批准的 additive `io` 字段草案，不是当前接口。新字段先经内部/测试使用，再在 CLI/MCP 的同一观察中透传；旧字段与返回类型不改。MCP.snapshot 当前有白名单式字段挑选，单改 daemon 不会自动透出全部新信息。[^LCM]

```json
{
  "io": {
    "generation": "<本次spawn的标识>",
    "read_offset": "<backend已交给session的累计字节数>",
    "fed_offset": "<session已交给流过滤器/parser的累计字节数>",
    "pending": {
      "known_payload_bytes": "<整数或null>",
      "readable_now": "<true/false/null>",
      "parser_incomplete": "<true/false/null>",
      "reply_bytes": "<整数>",
      "upstream": "unknown"
    },
    "local_cut": "drained | budget_limited | unknown | error",
    "representation": "posix_pty_stream | conpty_reconstructed_utf8",
    "stream_error": "<null或错误类别>",
    "basis_origin": "runtime"
  }
}
```

【我的推断／设计】`read_offset` / `fed_offset` 在同一 generation 内都以**backend交给session的字节域**计数，满足 `0 ≤ fed_offset ≤ read_offset`；POSIX是PTY交付bytes，Windows是pywinpty返回str经UTF-8再编码的bytes，不是批次数。reader队列中还未交给session的数据由pending另计。`fed_offset`只表示已送入流过滤器/parser，不表示每个字节已经形成屏幕内容；半CSI、半UTF-8及合法丢弃仍需parser状态/错误记录。frame revision在同步feed返回并完成本轮状态发布时增加，不与字节offset混用。这些水位不是业务因果或原始子进程 stdout byte offset。Windows 的字段必须写 `conpty_reconstructed_utf8`；其 upstream 始终可为 unknown。不能以“队列现为 0”填 `upstream=empty`。POSIX 可以报告“这次 select 未就绪”，也不能承诺将来不会到达字节。

【我的推断／设计】预算恰好用完时，即使尚未证明还有数据，也标 `budget_limited`，下轮执行一次真实非阻塞空检查后才转 local drained。未知数量用 null 而非 0；已知有数据但不知道字节数，可用 `readable_now=true`。不要让调用方用 `pending_bytes or 0` 合并这两种状态。

【我的推断／设计】T04 的 `_state != _GROUND` 可以指示该前置过滤器仍在序列中，但不能单独证明 pyte decoder / parser 没有缓冲。若无法从已审查接口取得 UTF-8 decoder 的未决状态，则 `parser_incomplete=null`，而不是通过 private field 猜一个 false。私有只读诊断可单独切片；不得改变 `_CSI_CAP=1024`、字符串保护或已确定的 SGR 降级行为。[^LCS][^L04]

### 4.1 readiness 不再把没读完当安静

【我的推断／设计】`STABLE` 的增强判断需要同时满足：当前观测切面 local drained、无已知 pending payload/reply/未完成控制序列、连续 quiet window 内没有新的相关变化、末尾复查仍满足。同一 poll 内的 interleave 若推进了 model/read_offset，原 wait 必须失效旧的 stability candidate，下轮重采样；不能在 poll hook 处理新数据后继续使用旧 quiet 起点。

【我的推断／设计】marker match 与流已完全消费分开。旧 `wait_for` 仍可报告“本次观察包含目标文字”；若此时 backlog 未空，应透出 `observation_scope=prefix` / io 状态，不升级为命令完成。不能把所有 marker 都改成等待 global quiet：持续更新程序可能永远不满足。新的“完成”profile 必须有应用 ACK、可信命令状态或独立裁判，而不是强行等 ConPTY 的未知上游变空。

【我的推断／设计】给 readiness 增加 optional pending/cut callback 属于 additive 公共签名提案；默认 None 保留既有调用。禁止注入伪字节 `b"\0"` 欺骗旧 `read_fn` 的“有输出”判断。callback 必须 O(1) 读取已提交状态，不再次 pump 或重新序列化整屏。[^S18]

## 5. service_io 必须放在三条路径，而不是另起 reader owner

【我的推断／设计】三条接入：worker 无请求时；正常请求之间；长 wait 自己已有的 read/poll 周期。三者使用同一 budget context，屏幕仍由那个 worker 修改。不从 on_poll 再递归进入 wait，也不让快请求的 `snapshot` 重置本轮 budget。

【我的推断／设计】拟议控制流（伪代码，非可直接替换源码）：

```text
worker iteration:
    取本轮配额
    若需service，有限推进本地已到达I/O；记录cut
    若关闭状态在进行，做允许的有界状态推进
    处理至多一个正常job（长wait仍用既有机制）
    若无job且local没有backlog，沿用有界阻塞等待
    若仍有backlog，安排下一有限轮；不无限drain

long-wait poll:
    使用同一配置的有限pump，更新cut/revision
    在poll gap中至多执行J_fast个既有快verb
    扫描至多J_scan项，遇到配额/时限就让出
    保留被跳过的long wait/resize顺序，不执行resize
```

【我的推断／设计】快请求的数量上限不等于执行时间上限。一个 `send_text` 会进入同步 write，一个 snapshot 会做整屏工作，一次 `_reply` 仍可能阻塞。`T_soft` 仅表示“检查点之后不启动下一工作”，不是可以抢占这些函数的硬截止。A05/A06 未改时不得宣称“所有请求下有界响应时延”。[^LCD][^LCB]

【我的推断／设计】不得为了预算直接使用 `list(jobs.queue)` 或绕开 Queue 的锁/unfinished task 计数。若为保持 deferred FIFO 需要新增内部 deque，属于新队列，必须写小提案；不能把这个细节藏进“三行优化”。配额测试必须覆盖“扫描很多不允许 interleave 的 job”而不只是执行计数。

## 6. 用户写入与设备应答的顺序

【证据支持·E1/E4】T03 证明一个生产 write 在真实 POSIX transport 上可完成而非假成功；它没有证明在 write 阻塞期间 owner 仍能服务 output。当前 pump 会直接调用 backend.write(reply)，且吞异常。[^L03][^LCB][^S17]

【我的推断／设计】最小规则：单写者；一个已经开始的逻辑输入不插入另一个用户输入或 reply；完整写完或记录部分失败后，才处理下一输入。先前读取生成的 device reply 应在后续新用户动作前处理，但不能插到上一输入的 UTF-8/escape/paste 中间。`send_line` 的 text 与 Enter 视作同一逻辑操作，不能在两者之间插入新业务按键。

【我的推断／设计】reply 的未写后缀必须有单独的有界槽位与进度记录。若 `IncompleteWrite.written_bytes` 已知，则只保留未写后缀；如果未知，不能自动重发整个 reply。应答失败将 `reply_status=failed/unconfirmed` 与 `action_permitted=false` 传给观察，不破坏已经成功解析的屏幕，也不吞掉后宣称设备查询完成。后续人工恢复或新 session 的路径必须显式，不能暗中“按一次 Esc”。

【我的推断／设计】输入写期间依赖自身 output 被消费的子进程仍可能形成双向等待。不能在本片里回调整个 `pump()`：那会在写进行时生成并写 reply，破坏顺序。需要新 tx 队列/异步 write 才能改进的部分单独提案；眼前方案应报告 partial/deadline，不把 timeout 后自动重试当恢复。相应新增交互实验列为 N2，不重跑既有 T03 256 KiB 实验。

【未确认】在附件的实现中，deadline 主要在 EINTR/EAGAIN/零进度分支检查，连续正数短写分支只增 offset；`select.select` 自己抛错时也可能绕过 `IncompleteWrite` 的封装。这是**新路径的 E1 观察与推断**，不否定已复核的 T03 E3/E4。生产 readiness 不得据此先许诺 write 一定 ≤5 s；N2 用假时钟与 select 抛错做新增窄测试。[^LCB]

## 7. close / EOF：请求、清理、确认分开

【我的推断／设计】关闭收据至少区分：
`close_requested`（停止接受新动作）、
`closing`（继续允许排空/完成已提交清理）、
`closed_confirmed`（本 profile 指定的 child exit、必要 reader 退出和资源释放均已观察）、
`close_unconfirmed`（截止到来仍有未确认项）。
`output_eof` 仅说明输出通道终止；不代替 child exit，不代替进程树清理。

【我的推断／设计】`close_unconfirmed` 必须包含未完成组件、known_pending、last_progress、generation 和可供现有 owner 定位的句柄身份；不能删除含 capability 的 registry、复用同一个 generation 或返回普通 closed 成功。在窗口已经关闭但仍无法确认后台子进程的情况下，也保持不确定。

【证据支持·E1】Windows 文档要求关闭 pseudoconsole 时排空或关闭 output pipe；build 26100 前后 native close 的返回行为不同。pywinpty `terminate(force=True)` 是否以可中断方式映射到该底层行为，本轮材料没有证明。[^S02][^LCB]

【我的推断／设计】因此“native close 调用后再检查 deadline”不能提供有界返回。若现有 API 会阻塞，方案只能是：沿用 daemon 隔离过程，通过已批准的 teardown worker 执行 native close，或另行批准外部生命周期监督；helper 不许修改 model，且每 session 数量受限。没有批准时，只交 close-contract 提案，不能将 Windows cap 默认开启并宣称 full-buffer close 已解决。

【我的推断／设计】正常关闭优先保留已交付数据；紧急取消可以停止记录/关闭输出通道来收敛，但必须报告 `tail_complete=false`、丢弃范围已知/未知，不声称 lossless。控制信号不得等待数据队列有空位。正常模式下禁止丢字节；强制中止是另一个被明确标记的操作，不是偷偷放宽同一验收。

## 8. 可实施切片：每片物理文件数 ≤7

【我的推断／设计】下表每行是一个独立授权单元；不是授权一次执行全表。canonical 与 vendor 各算一个物理文件，tests/run_all.py 与 MCP adapter 也计数。所有新测试采用同一注册策略，不临时塞进无关文件凑数。

| 切片／依赖 | 允许目标（最大数） | 可合入的承诺与失败测试 |
|---|---|---|
| P0 提案 | 0 个仓库文件；RUN 一份提案 | 审批预算接口/状态字段/新buffer/可能teardown helper；未批停止 |
| S1 预算传输基础 | backend+session 两个 canonical、两个 twins；`tests/test_a04_read_budget.py`；run_all：6 | 原 `pump()` 默认路径不变；budget profile 暂不在 daemon 启用。fake backend 多次有限读取拼接等于已交付序列；旧签名不受影响；强制unbounded变体失败 |
| S2 readiness 消费 cut（依赖 S1） | readiness+session canonical/twins；`tests/test_a04_pending_readiness.py`；run_all：6 | budget exhausted 不被判 stable；poll hook 更新造成旧 quiet candidate 作废；取消/超时路径不能被伪数据污染 |
| S2p parser 可见性（按需要独立） | screen_model canonical/twin；`tests/test_a04_parser_pending.py`；run_all：4 | 只增加私有只读诊断，T04 行为不变；半CSI/半UTF8必须 true或unknown，绝不假false；若无法可靠检查，明确unknown |
| S3 daemon service 与 io 透传（依赖 S1/S2） | tui.py、mcp_server.py；`tests/test_a04_daemon_service.py`、`tests/test_a04_io_surface.py`；run_all：5 | 没请求也推进；队列持续有快请求时也推进；旧interleave与resize排除不变；CLI/MCP不丢io依据 |
| S4 有界关闭协议（Windows S5 启用前） | backend+session canonical/twins；tui.py；`tests/test_a04_close_state.py`；run_all：7 | stop/EOF旁路；清理未确认不抹registry；卡住native操作不在owner假装被deadline中断。新线程须独立批准 |
| S5 Windows 字节积压（依赖 S1/S4） | backend canonical/twin；`tests/test_a04_winpty_backlog.py`；run_all：4 | 已交付再编码流不丢不重；queue+held均记账；旧reader不污染新generation；cap满时停止路径成立 |
| S6 设备应答进度（依赖 S1/S4） | session canonical/twin；tui.py；`tests/test_a04_reply_order.py`；run_all：5 | partial reply 不重复，错误可见；完整输入不能被 reply 插入；原设备应答继续成立 |
| S7 发行/支持说明（相关切片完成后） | 发布者另批准最多7个明确文件 | 不改映射、不改entrypoint、不改依赖；wheel/skill 独立导入 fingerprint；E6未运行则不能打发布已验证标签 |

【我的推断／设计】S1/S2 可先合入被动能力，但不代表 A04 完成。S3 的 POSIX idle-liveness 可以单独取得 E4；Windows 总体要等 S4/S5，不以 POSIX 成功代签。S6/A05/A06 若未交付，则发布说明和 conformance scope 必须写出限制；不能用“后续工作”掩饰已有阻塞条件。

## 9. 逐失败测试矩阵

| 测试 ID | 负例／故障注入 | 必须成立的判据 | 平台/证据目标 |
|---|---|---|---|
| IO-01 | 后端持续可读，不会自然empty | 每轮≤预算，拼接完整已交付流；删除预算变红 | E3 两平台模型/生产方法；不替代 E4 |
| IO-02 | 截在 CSI/UTF-8 中，当前一次恰好没输出 | `local_cut` 非drained或parser未决；不返回完整安静保证 | E3，保留 T04 |
| IO-03 | 无任何 client job 的有限输出fixture | daemon而非测试体自行服务；禁掉idle service变红 | E3 fake-loop + N1 E4 |
| IO-04 | 持续fast jobs + 一个long wait | I/O和允许快verb均有服务机会；resize未执行；禁掉配额/保留机制变红 | E3 注入，不硬填毫秒指标 |
| IO-05 | reader cap不足接纳整个chunk | suffix只投递一次；queue+held满足已批上界；丢尾/重发均变红 | E3；N1 Windows E4只测新增机制 |
| IO-06 | 队列满时close、EOF及reader晚返回 | 控制不被data挤住；迟到数据不能进新generation；unconfirmed不被改成closed | E3；N1按批准native profile |
| IO-07 | reply写一部分再失败，后面排用户输入 | 报已知prefix，停止冲突输入，不自动整包重发；吞error变红 | E3，N2窄交互 |
| IO-08 | native close/read不返回 | supervisor截止后有close_unconfirmed证据；不得报告EOF/exit已确认 | E3；E4必须受独立资源上限 |
| IO-09 | 旧后端签名、内部TypeError | 默认调用零参数；内部错误不被fallback掩盖 | E3 |
| IO-10 | CLI→daemon→MCP各读同一frame | `io` 与屏幕cut同源；wrapper不得自行填runtime依据 | E3 + 待批准E6 |

【我的推断／设计】所有“变红”只在隔离验证副本做针对性故障变体；同一测试文件hash保持不变。对已完成 T03/T04/T05 不再重跑原测量；在新代码改动后运行相关既有回归属于防回退，不等于重新质疑旧事实。

## 10. Windows 投递缺口不能由 queue cap 修复的部分

【证据支持·E4】接受 X2 的实际投递观测和当前 ConPTY 路径不能提供 child原始输出 byte-exact 的产品边界，不试图用输出字节计数“追回”被合成的历史。[^LX2]

【我的推断／设计】cap 只能管理 SmartCLI 已接到的 str/再编码 bytes；不能恢复 ConPTY 之前的 child-write 分片、原始数量、时序或已经不在当前画面的历史。它限制 reader 进一步取数，不证明 child 会等速降产。分别发布：
`source_wire_exact=false`（当前 Windows profile）；
`delivered_stream_preserved`（本运行时本次接收后的完整性）；
`screen_model_consistent`（同一交付流/宽度profile的屏幕一致性）。
后两项仍需各自测试，不能从第一项 false 推导全部无用，也不能反推第一项 true。

【未确认】现有观测没有将 native合成、native缓存和pywinpty返回批次的具体时延占比分离；不能把所有延迟归因给某个函数，也不能说某条历史在所有实现/所有时间都一定永不出现。无需为此重跑 X2；本片只对自己接收到的流和状态负责。


---
## 来源定位

[^L00]: 附件 `SmartCLI_v3_Upload/README_FIRST.md`，事实基线摘要、Owner 提醒。E1/E3/E4 分别标注；HEAD 仍是基线，但本轮实现位于未提交工作树。收到并阅读：2026-09-16。

[^L03]: 附件 `SmartCLI_v3_Upload/03_receipts/T03_closure.json`，first_results、mutation_cycle、claim。E3 注入 + E4 本机 POSIX library；叙述 44 次等待。收到并阅读：2026-09-16。

[^L04]: 附件 `SmartCLI_v3_Upload/03_receipts/T04_closure.json`，evidence_scope、mutation_cycle、controls。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^L05]: 附件 `SmartCLI_v3_Upload/03_receipts/T05_closure.json`，evidence_scope、mutation_cycle、changed_files。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^LCB]: 附件 `SmartCLI_v3_Upload/04_code/pty_backend.py_T03_implemented.py`，PtyBackend、WinptyBackend._read_loop/read_nonblocking/terminate、PosixPtyBackend.write。E1 本轮实现源码，T03 已落地；不以远端旧代码覆盖。收到并阅读：2026-09-16。

[^LCD]: 附件 `SmartCLI_v3_Upload/04_code/tui.py_CURRENT_daemon_A04_target.py`，_serve_forever、worker、INTERLEAVE_OK、_drain_interleavable、_reply、_snapshot_response、cmd_close。E1 当前 daemon 源码；既有 interleave/resize 排除必须保留。收到并阅读：2026-09-16。

[^LCM]: 附件 `SmartCLI_v3_Upload/04_code/mcp_server.py_CURRENT.py`，_call_session、snapshot、start/close。E1 当前 MCP 适配源码；不要把适配器自己填的依据冒充 runtime 依据。收到并阅读：2026-09-16。

[^LCS]: 附件 `SmartCLI_v3_Upload/04_code/screen_model.py_T04_implemented.py`，_ByteStream.feed/_state、ScreenModel.feed/drain_replies/visual_hash。E1 本轮实现源码，T04 已落地。收到并阅读：2026-09-16。

[^LP]: 附件 `SmartCLI_v3_Upload/03_receipts/A04P_PROPOSAL.md`，§2 三切片、§3 未修项、§4 验收。提案不是实现证明；局部论断 E1/推断，数字引用 LX2/LX3。收到并阅读：2026-09-16。

[^LPD]: 附件 `SmartCLI_v3_Upload/03_receipts/A04P_DESIGN_DELTA.md`，§1 模型边界、§2 符号、§3 文件清单。E2 原型结论；不是产品实现。收到并阅读：2026-09-16。

[^LPL]: 附件 `SmartCLI_v3_Upload/03_receipts/A04P_last.md`，Invariants、NOT_RUN matrix。E2 原型收据；E4 基线另见 LX2/LX3。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

[^S02]: 【证据支持·E1】[Microsoft：ClosePseudoConsole](https://learn.microsoft.com/en-us/windows/console/closepseudoconsole)。E1 官方文档；关闭时继续输出，build 26100 前后返回行为，输出管道排空。访问：2026-09-16。

[^S17]: 【证据支持·E1】[SmartCLI：PtySession（基线未改模块）](https://github.com/dwgx/SmartCLI/blob/701e61f6d69aa2420617edf80b1136df8d5e8cf7/smartcli_core/session.py)。E1 源码；pump read→feed→reply，send_line 分两次写；不取代附件中三个已修改模块。访问：2026-09-16。

[^S18]: 【证据支持·E1】[SmartCLI：readiness（基线未改模块）](https://github.com/dwgx/SmartCLI/blob/701e61f6d69aa2420617edf80b1136df8d5e8cf7/smartcli_core/readiness.py)。E1 源码；read_fn/hash/marker/on_poll；附件未附该文件，采用已读固定基线。访问：2026-09-16。

