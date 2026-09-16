# BENCHMARK_MIN — 可辩护的一日最小基准，而非性能排行榜

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 1. 第一版只回答一个问题

【我的推断／设计】第一版回答：**在相同任务、权限、模型和预算下，这个运行时是否把可确认的结果交给 Agent；没有证据时是否拒绝假成功？** 不回答“谁是全球最强终端 Agent”。T03/T04/T05 与 X2/X3 的既有 E3/E4 作为输入条件引用，不再当作新基准试验重复。[^L03][^L04][^L05][^LX2][^LX3]

【我的推断／设计】一天版本是**范围与资源盒**：最多8小时人工工程投入、最多3小时顺序执行时间、一个活动 PTY、零自动重试。没有现成模型凭据、没有目标运行时可用版本、没有获准原生环境时，以 `BLOCKED/NOT_RUN` 收尾，不以临时云服务或换模型补齐。该上限不是本轮能保证的开发工期。

【我的推断／设计】先锁定协议、fixture 与独立裁判，再接一个 SmartCLI 适配器。第二个适配器可选 Microsoft tui-test 或 A04 候选；做不完就交付单产品证据，不硬造横向排名。用一个轻量多模式 fixture 实现三类小任务，避免第一天建三个复杂应用。不要加入外网、编译大项目或执行生产数据库操作。

## 2. 最小任务：三个任务共享一个受控应用

【我的推断／设计】拟新增 `tools/bench_min/fixture.py`，标准库实现交互状态机；持有私有 task state，公开 VT 界面，可选开放受限应用适配端口。严格 UI 的输入仍经真实 PTY／ConPTY，不能用内存函数直接调用代替。它不是 Vim，不将模式切换结果称为 Vim 能力。目标平台的 raw 输入处理需要本地实现并验证。

| 任务 | Agent 看到与需要完成的事 | 裁判预期，非 Agent 自述 | 必须放入的混淆项 |
|---|---|---|---|
| B1 中文菜单保存 | 三项菜单顺序由 seed 决定；选择“保存”并确认指定配置 | 独立状态文件中 `saved=true`、目标值正确、动作次数符合合法轨迹 | 标题/状态栏粗体；旧“保存成功”文本；不允许靠字面出现就结束 |
| B2 模态编辑与验证 | 浏览/编辑模式切换，修改一个指定字段，再保存并退出 | 精确文件内容与格式；退出或关闭状态独立记录；未改字段保持原样 | 同一按键在两模式下不同含义；未保存缓冲与磁盘不同 |
| B3 等待、诊断与恢复 | 有限后台输出后出现带 run nonce 的当前提示；一次可恢复错误后完成工作 | 结果状态与唯一run一致；不能把旧marker、单纯quiet或取消通知当完成 | 输出内容可重复；错误后必须观察；有未完成等待可请求取消 |

【我的推断／设计】fixture 的任务目标、状态转移与裁判规则必须在运行前固定。nonce 由评测器生成，只通过任务允许的界面／适配接口展示；真实 expected result 不送给模型。B3 的取消能力若产品不支持，作为明确子项 `UNSUPPORTED`，不得由 harness 偷偷杀进程后宣称 runtime 支持 waiter cancellation。

【我的推断／设计】独立 judge 只读由 fixture 写入的私有状态，校验run_id、任务seed、最终结果与事件合法性；不读取 Agent “我完成了”的文本作为成功依据。第一版普通本机进程隔离不构成防恶意 Agent 沙箱。若 Agent 与 judge 同用户可互改文件，应声明 `adversarial_isolation=false`；不能声称已验证对抗作弊安全。应用在文件工具赛道允许的输出目录与裁判目录必须分开。

## 3. 三赛道：同一目标，不同权限，绝不混合排序

【我的推断／设计】每个 episode 的工具清单必须冻结并打印，不能只用提示词说“请勿读文件”。工具授权由评测器实际实施。

| 赛道 | 允许 | 禁止 | 可以比较的结论 |
|---|---|---|---|
| U：严格 UI | runtime 的观察、键/文字/鼠标、wait、允许的恢复；fixture 由 supervisor 启动 | 通用 shell、读写文件、应用私有状态、RPC/直接函数调用 | 该终端工具下的界面操作结果与误确认 |
| A：应用适配 | U全部 + 明示的 `read_view/act` 之类受限应用接口 | 私有 judge／结果文件、未登记的内部状态 | 适配辅助的任务效果；须报告新增语义与适配工作量 |
| H：API／文件混合 | 已登记API与工作目录文件工具，允许绕开UI实现目标 | 裁判私有目录、未授权网络与宿主资源 | 实际混合工作流效率，不能反推“会用TUI” |

【我的推断／设计】H赛道不能借降低任务目标赚分：仍检查保存内容与不该改变的字段。U赛道不得为了匹配工具数把一个 runtime 的多个内部动作藏到“万能脚本”里；如果有组合操作，要打印组合中的实际动作数与资源支出。适配动作比按键更强，故A/H不与U汇成一个总成功率。

## 4. 冻结配置：缺一个关键字段就不启动模型

【我的推断／设计】拟新增 `plan.json`，由本地读取 owner 已批准的模型配置后写入具体值。不要把聊天模型名称、`latest` 别名或猜测的 seed 支持写进去。以下是规格示意，不是可直接带占位符运行的配置：

```json
{
  "model": {
    "provider": "<approved provider>",
    "model_id": "<literal returned/resolved model identifier>",
    "revision": "<provider revision, or explicitly unavailable>",
    "temperature": 0,
    "seed_support": "supported | unavailable",
    "system_prompt_sha256": "<fixed>",
    "tool_schema_sha256": "<fixed>"
  },
  "episodes": {
    "tasks": ["B1", "B2", "B3"],
    "tracks": ["U", "A", "H"],
    "fixture_seeds": [17, 29, 43],
    "max_retries": 0
  },
  "budget": {
    "max_tool_calls": 24,
    "max_model_input_tokens_total": 96000,
    "max_model_output_tokens_total": 12000,
    "max_observation_utf8_bytes_per_call": 8192,
    "episode_wall_seconds": 120,
    "cleanup_wall_seconds": 10,
    "run_wall_seconds": 10800,
    "max_live_pty": 1,
    "max_fixture_output_bytes": 1048576
  },
  "geometry": {"cols": 80, "rows": 24},
  "spend_cap": "<explicit owner-approved amount and currency>"
}
```

【我的推断／设计】以上数字全部是建议的**预注册预算**，不是测量或放宽既有阈值。owner 可以在开始之前收紧；不能在看到失败后改预算继续同一试验。若provider不提供精确token计数，保留其返回值并标未知，额外用文本字节上限防无限输出；不把字符数称为token。不能跨provider声称temperature或seed语义完全等价。若所选API不接受temperature等参数，预注册时标为unsupported并不发送；不能看到执行失败后换模型、换参数继续算作同一实验。

【我的推断／设计】固定 provider、literal model id、请求参数、system prompt、工具说明、观察格式与adapter版本。seed主要冻结fixture与顺序；服务端不能固定模型seed时写 `unavailable`，保留每次请求/响应ID和原始输出。没有精确模型revision并不使试验无价值，但必须收窄为“该时间窗与返回model id下”，不能承诺逐字可复现。

【我的推断／设计】记录总输入token时应包含历史上下文重复发送、工具schema、观察与失败重试；不能只计最终答案。比较观察压缩方案时仍保持同样per-episode总预算，并报告截断次数与丢失信息；不要因为一方省略样式而只展示更低token数。

## 5. 数量与一日实施上限

【我的推断／设计】一个 runtime：3任务×3赛道×3fixture seeds＝27个预注册episode。两个runtime最多54个，顺序执行；120秒任务上限加10秒清理，上限约117分钟纯episode时间，仍受3小时总执行盒约束。这是配置上界的算术，不是任何产品实测耗时。执行盒耗尽后剩余项记 `NOT_RUN_BUDGET`，不能只公布完成的简单任务。

【我的推断／设计】先运行judge的错误答案负例，再做每赛道一个fixture检查；这些属于评测器验证，不计模型episode分母，也不用于调整同一任务的评分答案。若fixture自身错误，停止整项并标记污染范围，修复后新建新的实验版本，不把前一次失败静默删除。

| 投入盒（设计上限） | 工作 | 到期交付／停止 |
|---|---|---|
| 0–2工程小时 | 单fixture、独立judge、错误结果拒绝测试 | judge可被假成功骗过则停止，不启动模型 |
| 2–4工程小时 | 接SmartCLI adapter、工具权限和证据输出 | 原生启动/关闭不受控则NOT_RUN，禁止多会话排障 |
| 4–5工程小时 | 冻结配置与无模型控制检查 | 模型费用/身份未明确则BLOCKED |
| 剩余工程盒 | 顺序运行27项；第二adapter只在已可用且有预算时加入 | 3小时执行硬停，8小时工程盒结束，保存所有缺项 |

【我的推断／设计】这不是要求本地在一天内写完一个通用harness。第一版不接入五个竞品、不造多主机调度器、不做自动发现插件、不跑Windows×Linux×macOS全矩阵。先在一个被批准的平台证明评测器成立；其他平台完整标 `NOT_RUN`。

## 6. 结果必须怎样统计

【我的推断／设计】每个episode保存互相独立的结果列：`goal_correct`、`claimed_complete`、`completion_basis_valid`、`cleanup_converged`、`diagnostics_complete`。主指标“有依据地完成”要求前三者一致且依据有效；单列**错误宣告完成**数量，不能把它与普通超时混为一类。还有一种合法结果是“未确认，拒绝声称完成”，它不是任务成功，但比错误宣告完成在安全维度上不同。

【我的推断／设计】所有已启动episode进入预注册分母，包括超时、工具异常、预算耗尽和清理失败。未启动、provider故障、fixture失效分别报告，不能与任务失败混写，也不能不披露地删掉。若裁判失效，不能按Agent自述补判。

【证据支持·E1】NIST给出了二项比例区间的计算方法，包括Wilson形式；点估计本身不能表达小样本不确定性。[^S15]

【我的推断／设计】当独立Bernoulli假设可以说明时，报告 `k/n`、Wilson区间和置信水平，计算应保留代码/公式。设 `p=k/n`，预先确定标准正态分位数 `z`，区间为：
\[
\frac{p+z^2/(2n)\ \pm\ z\sqrt{p(1-p)/n+z^2/(4n^2)}}{1+z^2/n}.
\]
本文件不代入任何虚构成功次数。只有一个episode时应写“该固定实例一次通过”，不写“成功率100%”。

【我的推断／设计】同任务三个seed不是广泛任务总体的三个随机样本；同provider同模型重复也可能相关。第一版优先逐任务逐赛道列3次原始结果，不将27个高度相关episode当作全球成功率样本。若汇总，只称“此固定任务集完成k/n”，并说明任务权重；跨任务的宏平均与逐episode微平均分开，不用一个区间掩盖任务差异。

【我的推断／设计】两runtime使用成对的task/track/seed，并交替先后顺序；报告成对“双方过／只有A过／只有B过／双方未过”。延迟只在**同样正确完成**的配对上比较，失败episode耗时单列；同时报告全部episode预算消耗，避免某方更早失败反而“更快”。三个seed不适合声称尾延迟p99或稳定显著胜出。

## 7. 五个评测器自身的拒绝测试

【我的推断／设计】这些必须先绿才允许花模型预算，测试目标是真正judge/verifier：

| 错误注入 | 必须结果 |
|---|---|
| Agent输出“已保存”，文件未变 | `goal_correct=false`，不能PASS |
| 文件正确但来自前一个run/seed | `INVALID_EVIDENCE` |
| fixture完成但runtime只给quiet，adapter伪填app_ack | `completion_basis_valid=false`，goal与basis分列 |
| 严格UI试图读取工作文件或调用application API | 工具层拒绝；违规轨迹不得计严格UI成功 |
| 取消响应后仍有旧输入被投递，导致额外修改 | `cleanup/control_convergence=false`，保留重复动作证据 |

【我的推断／设计】fixture最终状态正确不代表动作从未重复：例如“保存同一个值两次”可以掩盖重发。至少一条任务动作必须留下append-only的非幂等计数或事件ID，裁判检查一次接受次数，且不给Agent覆盖该证据的权限。对无应用ACK的一般程序，不因此承诺exactly-once；这里只测受控fixture。

## 8. 可执行接口与当前未运行项

【我的推断／设计】下列为W3待实现接口，文件存在并经审查后才能运行；不得把这些命令当当前SmartCLI已提供的产品子命令：

```text
python -B tools/bench_min/run.py validate --plan <PLAN_JSON>
python -B tools/bench_min/run.py judge-selftest --out <NEW_RUN/judge-first.json>
python -B tools/bench_min/run.py run --plan <PLAN_JSON> --out <NEW_RUN/episodes>
python -B tools/bench_min/run.py report --from <NEW_RUN/episodes> --out <NEW_RUN/report.json>
```

【我的推断／设计】报告最上方必须写：运行时commit+overlay、模型literal id、平台/profile、fixture/judge hash、预注册/启动/有效episode数量、首次执行日期与预算、费用是否完整、是否存在未确认清理。Microsoft等竞争实现只能在真实adapter运行后进入E5对照，不从README功能表填结果。

【未确认】本轮未实现或执行这个新基准，没有模型调用，没有竞品运行，没有费用/成功率/性能数值。Windows、POSIX、macOS的本基准覆盖均为 `NOT_RUN`；这不降低附件既有E3/E4证据的等级。


---
## 来源定位

[^L03]: 附件 `SmartCLI_v3_Upload/03_receipts/T03_closure.json`，first_results、mutation_cycle、claim。E3 注入 + E4 本机 POSIX library；叙述 44 次等待。收到并阅读：2026-09-16。

[^L04]: 附件 `SmartCLI_v3_Upload/03_receipts/T04_closure.json`，evidence_scope、mutation_cycle、controls。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^L05]: 附件 `SmartCLI_v3_Upload/03_receipts/T05_closure.json`，evidence_scope、mutation_cycle、changed_files。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

[^S15]: 【证据支持·E1】[NIST：Confidence intervals for a proportion](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)。E1 官方统计手册；二项比例区间，适用前提必须声明。访问：2026-09-16。

