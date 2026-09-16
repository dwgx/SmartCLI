# A04_DESIGN — 保留现有调度，分平台消除空闲故障
依据：[L1 §4，E1]；[L1 §6，E1]；[SC2/SC3/SC4，E1]。**用户 Windows 上的内存增长、POSIX 子进程阻塞仍是源码支持的推断，不写成已测 RSS 或时延。**

## 1. v1 的修订，而非 actor 重写
问题不是“没有 reader”，而是：Windows 已排空到无界 queue，但无人消费到模型；POSIX 空闲时 master fd 无人读。现有 long wait 会调用 `pump`，并通过 `on_poll → _drain_interleavable` 回答快请求。这条路径必须先锁测试，再渐进改造。

统一契约：**只要会话仍在服务、且在配置的吞吐/资源范围内，不论有没有客户轮询，输出均按序进入模型；每次工作有预算，模型仅由单 owner 修改；过载、积压和不完整明确可见。** 不能承诺无限快生产者永不被阻塞、有界内存和永不丢字节同时成立。生产者背压是合法过载行为，空闲无人服务导致停滞不是。

## 2. 资源边界（建议初值，不是测量）
| 项 | 初始设计 | 精确定义 |
|---|---:|---|
| 每会话 ingress payload | 256 KiB | 所有已接收、尚未被模型提交的标准化字节；包含队列和 consumer staging |
| 高/低水位 | 192 / 64 KiB | 高水位暂停进一步读取，低水位允许恢复；并另有硬上限 |
| 入队 fragment | ≤4 KiB | 以 bytes 计，不能用 Queue(maxsize=项数) 冒充 byte cap |
| 单 owner turn 解析 | 最多32 KiB、每片≤4 KiB | 片后检查协作时间预算；预算耗尽让出处理机会 |
| 空闲唤醒 | 10ms 候选上限 | 设计目标；可用事件唤醒优先，实际 P95/P99 另测 |
| CPU soft budget | 2ms/turn 候选 | 非硬抢占；一次 pyte.feed 超预算要测量/诊断，不能宣称绝不会超时 |
| 请求/回复/设备应答 | 各自独立有界 | 原型分别用小容量测试；不可只给 ingress 上限而忽略其他队列 |
| EOF/control | 独立有限状态 | 不能把 EOF sentinel 塞进已满 data queue 后永久等不到关闭 |

上述是模型可计费 payload，不是进程 RSS 上限。Python 对象、decoded str、UTF-8 重编码临时副本、库内缓冲和操作系统 pipe 均另列。Windows 返回 str 时一次 native read 必须限长并审查实际返回界限；若违反，不能先无界接收再称队列有界。

## 3. Windows：保留现有 reader，改变流量和生命周期
reader 只读取、转换为当前后端标准化 UTF-8、提交有界片，不触摸 pyte。owner 持续从有界 buffer 取字节送入模型。队列满时使用 Condition/Event 的 stop-aware 等待，不在锁中阻塞 native read，不静默丢开头／尾部，不丢 UTF-8 或 escape 中段。

当 `pywinpty.read` 返回 str，本层重编码不代表拿到了原始 ConPTY 字节。因此 `wire_exact=true` 不适用于任意二进制；本轮 byte-exact 的模拟 POSIX 测试不能顺带证明 Windows binary path。[SC2，E1]

关闭：先标 CLOSING、拒绝新用户动作并唤醒所有 data/condition 等待者；继续消费可用最终输出；有限期内收尾 reader 和目标。若不支持打断 native read，超时必须留下 `close_unconfirmed`，不能让 callback 越代写入复用队列。reader 应持有本次 spawn 的 queue/proc/generation，而非在旧线程中不断解引用可被新 spawn 换掉的 `self._queue`。

不要无条件把旧 ConPTY 文档泛化到所有 Windows：官方 `ClosePseudoConsole` 页面说明 Windows 11 24H2/build26100 起函数立即返回，早期版本行为不同；应用仍需要确认输出 pipe 关闭及客户端退出。实际 pywinpty/lib版本与 OS build 都写报告，不以 API 返回代替 child exited。[STD4/STD5，E1]

### 对首帧／CPU峰值的回答
只把 queue 设为有界，不自动降低首帧时延；等待满队列还能推迟生产者输出。必须同时有持续 owner 消费，才减少“首个 snapshot 才解析全部积压”的设计缺陷。按片解析可以约束单 turn 的工作量，但不保证 CPU 峰值下降；持续解析会把原来延迟到请求时的工作提前，并可能增加空闲运行时 CPU。

应测 `first_byte_to_parsed_frame`、`snapshot_queue_delay`、每 turn bytes/time、max pending payload、进程RSS趋势，报告 baseline与candidate同负载。已有3秒ConPTY启动安静窗口是另一因素，不能把它算作此修复必然消除。

## 4. POSIX：只能 owner 读取 master fd
不要再起第二个 parse/pump 线程。原型让 owner 在 `jobs.get` 没任务时也执行有界 `service_io`；长 wait 的 `read_fn` 也调同一条路径。因此空闲、请求、wait 三种路径都消费同一流，但不能互相递归进入 owner。

不能只在 `queue.Empty` 加 `sess.pump()` 就宣布完成：当前 `read_nonblocking()` 自身 drain-until-empty，持续生产可令一次调用几乎不返回；现有 wait 仍可能使用这条无界路径。必须给 backend read／session pump 新增**可选预算**，或在 private adapter 中实现同等能力，旧调用签名/返回值维持兼容。read耗尽配额后不虚构“屏幕稳定”；等待 readiness 还需检查 pending/backlog，不能拿预算截断的片段当完整 frame。

CPR/DA：当前 pump 会收集回复并写回，保留该行为。设备回复也需有界；用户输入和设备回复必须在明确的写入单元边界排序，不能在一半 UTF-8/键序列/粘贴中无条件插队。若回复无法写完，应记录有界故障而非静默声称已应答；T03 是其生产完整性前置之一。

## 5. 两个 watcher 谁读？答案是：都不读
只读 watcher 保存各自谓词、起始 revision/geometry、deadline/cancel，不调用 `os.read` 或 ConPTY.read。owner 更新模型，产生一个不可变观察，在这同一观察上分别判断 A、B；wake A 不消费掉 B 的事件。

但**本原型不新建多 watcher 产品 API**。先保留 legacy“一条长wait+快操作interleave”，加假时钟测试证明它未退化。多独立长 wait 属于后续 T10 的范围，不能混到 A04 修复里。

## 6. interleave / resize 回归矩阵
| 情况 | 旧行为应保留 | 原型如何证明 |
|---|---|---|
| 长 wait 中 snapshot/alive | poll gap 中响应，同一 session owner | 记录线程 ident；移除 hook 后测试失败 |
| 长 wait 中 send_text/send_line/send_keys | 按已接受请求顺序处理 | fake backend 字节序列对比，不拆分不同请求字节 |
| 并发 resize | legacy wait 期间延后，不混入成功证据 | 只有 resize、没有相关输出时不能被报告为按键成功 |
| 第二个长wait | 现有接口仍排队 | 不假称已经支持多 watcher |
| 慢 reply | 现有timeout60s是边界，不是无界 | 原型模拟 slow writer；未解决时明确关联 A06，而非宣告全部公平 |

`INTERLEAVE_OK` 中虽然有 `list`，当前 `_handle` 没有对应有效 list 分支；list_sessions 的实际路径在客户端。保留有效 API 不等于新增并承诺一个不可调用的 verb。[SC3，E1]

每 turn 排空 interleave jobs 也必须有个数／时间预算，否则快请求洪水会耗尽 poll gap。若这要求改变旧请求顺序，单独记录测试，不在 A04 中偷偷放宽。

## 7. 溢出/失效规则
满队列：背压，不丢字节。长期过载：显式 `backpressured` 与 age 指标，可超时失败或由操作者终止；不存在无限磁盘兜底。若驱动报告已经丢失原始输出，置 `observation_incomplete`，拒绝该片段上需要完整性的成功确认。全屏 repaint 不保证恢复 parser/mode/两屏状态，不能随便把不完整清零。

首两个 release 不新增原始全量录制器来掩盖溢出；已有日志/截图复用，不发明无限历史服务。

## 8. 两套最小负例及证据范围
Windows **纯模型 E2**：容量12、chunk4，producer 提交20字节、consumer每tick最多4字节。关掉consumer可进入backpressure但pending永不超12；启用后顺序精确；满buffer时close控制状态仍可送达，缓冲可继续排空，最终输出在EOF前仍能接收。纯模型不证明真实线程被唤醒；唤醒与native关闭必须由后续批准的并发测试证明。还原无界版本必须破坏预算断言。该测试不是RSS验证。

POSIX **注入式 core/loopback E3候选**：fake fd 在无人请求时持续可读，owner空闲tick必须处理完有限payload并形成CPR回复；停用idle service后完成断言失败；两watcher不得增添read调用者。E4另用一个有限输出子进程+独立终止标志；不靠“sleep后没输出”当裁判。

本轮 worker C 只交纯内存/假时钟原型。真实 socket线程和ConPTY/PTY实验需当前owner明确批准。生产改动按独立小增量分 backend budget → owner接线 → lifecycle，不许一次合入整套 actor。
