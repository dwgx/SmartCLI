# POSITION_2026Q4 — 以可验证的交互契约定位，而不是堆满工具面

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 1. 时间与判断范围

【我的推断／设计】2026Q4是规划窗口，不是已经发生的发布。本文的外部材料访问日为2026-09-16；固定提交只用于稳定对照，不宣称是未来最新版本。两次release使用A/B代号，不擅自分配版本号、发布日期或发布授权。所有竞争产品性能、费用、任务成功率均未在本轮测量。

【证据支持·E3/E4】SmartCLI已有的本地优势证据是：具体中文span修复、SGR流式/语义修复、一次真实POSIX完整写入与负例，以及明确识别的Windows/Posix观察边界；它们尚不构成daemon修复、跨平台端到端任务或发行验证。[^L05][^L04][^L03][^LX2][^LX3]

【我的推断／设计】定位应从“又一个让Agent操作终端的工具”收紧到：**对持续终端交互给出带表示范围、输入进度和完成依据的结果；已知数据未处理、部分输入、取消竞争或关闭未确认时，不返回虚假的完成结论。** 这是一项待兑现的产品契约，不是已经超过任何竞品的宣言。

## 2. 正面对照：比较具体能力，不用形容词评分

| 对象／证据 | 已有可核查能力 | 需要正面承认的边界或重叠 | SmartCLI应验证的差异，非当前胜出结论 |
|---|---|---|---|
| Microsoft tui-test，E1 | Windows/Linux/macOS；CLI与Rust/Python/JS；locator、四类wait、输入和录制；README说明beta重写 | “Windows”“Python”“Agent可操作TUI”都不是SmartCLI相对它的独占点 | 同一任务下，对pending/partial/quiet/close的依据是否保真并拒绝错误答案；需E5，不用工具数推断 |
| coder/agent-tty，E1 | 长会话、带序号事件、文本/截图/录制、可重放证据路线 | 不应为追齐录制格式重建一整套视频工具；事件日志存在不自动证明磁盘持久性或任务正确 | 将已有截图工具绑定确切revision；明确原始/重构流与tail缺口；比较拒绝错误证据而非录像是否好看 |
| onesuper/tui-use，E1 | PTY持续onData喂xterm、snapshot、高亮、title、alt-screen与退出状态 | SmartCLI持续pump不是无人做过的创新；轻量CLI是同一类需求 | 显式区分已交付/已解析；预算与局部cut；不能以读取事件通知代替解析屏障 |
| tmux系，bnomei为例，E1 | MCP、session/pane管理、tracked command ID、旁路退出码、共享会话、可选SSH路由 | tmux/支持shell是实际前提；命令跟踪只适用其配置/包装范围，不等于任意TUI事务 | 无tmux本机后端仍保留；对没有shell完成信号的TUI返回未知；共享能力可选适配而非替代核心 |
| taria，E1 | 应用声明widget tree/可用动作，并用输入ID和ACK区分接受、忽略或未确认 | 需要应用配合；不是任意旧TUI自动具备语义树 | 通用屏幕与应用语义分层；有ACK才使用，没有则保持未知；native semantics不伪装成screen inference |

【证据支持·E1】表中外部功能分别由固定源码/README支持：Microsoft入口及engine；coder的README及EventLog；tui-use的Session；bnomei的README/tmux adapter；taria的README。没有任何一行是本轮竞品运行结果。[^S19][^S20][^S21][^S22][^S23][^S24][^S27][^S25]

【我的推断／设计】对应实验必须使用相同task、track与judge；未知项留空或写NOT_RUN，不能折算成0分。SmartCLI被审计得更深、问题列得更多，也不能因此当作“客观更差”；对方README列得更多同样不证明可靠性更高。

## 3. 对竞品源码的具体取舍

### 3.1 Microsoft：学显式操作，检查具体完成分支

【证据支持·E1】所读取 `command_settled` 在tracker未启动时使用300ms quiet条件，另外检查取消、退出与tracker状态；这是固定engine函数行为。[^S20]

【我的推断／设计】SmartCLI应从中学习把wait类型分开，但进一步要求返回依据来源，避免调用者把quiet fallback理解成已确认exit。不能由这一个函数判定Microsoft整体取消行为错误，必须阅读调用层并实测后再作结论。也不要仅为了“更严格”永远返回unknown：正确的有ACK／结果的任务应在预算内完成。

### 3.2 agent-tty：学事件有序与失败显性，不把日志当外部事务

【证据支持·E1】`EventLog.append`维护事件seq、验证payload、串行化append，并对写入错误进行处理；源码也考虑日志中可能含秘密的权限。[^S22]

【我的推断／设计】先保证自身证据的完整性和来源，再做丰富导出。不能因为有append就承诺fsync级持久性，也不能把日志提交与已经发生的PTY副作用说成原子事务。SmartCLI应先具备“缺事件时拒绝完整回放”的测试，而非直接增加WebM支持。

### 3.3 tui-use：学持续消费，不复制不明确的屏障

【证据支持·E1】所读Session在onData里先调用 `terminal.write(data)` 再通知listeners；xterm的write是异步缓冲处理。这个顺序不单独证明每次通知时parser已经完成。[^S23][^S07]

【我的推断／设计】这是一项要检查的时序边界，不是本轮复现的竞品bug。SmartCLI应让read revision与fed revision明确，后续引入异步引擎时也不破坏观察契约。本轮继续使用pyte，不借此扩大默认引擎迁移范围。

### 3.4 tmux与taria：优先组合，不重复实现它们擅长的宿主/应用能力

【我的推断／设计】已有tmux会话适合可选宿主适配；已有taria应用适合语义适配。SmartCLI的通用核心应输出二者都能解释的“已观测、已提交、已确认、未知”状态，而不是强制所有任务经同一抓屏路径。专用适配的任务成绩放A赛道；调用文件/API放H赛道，不能拿来提高严格UI成绩。[^S11][^S25]

## 4. 两次release的承诺与不承诺

### Release A：正确观察 + 有范围的持续服务

【我的推断／设计】Release A的主张是：保留T05/T04/T03已确认行为；已批准后在内置后端提供预算化消费与pending/cut；daemon空闲、请求间、长wait路径保持服务机会；已有interleave与resize排除不退化。Windows只承诺控制已交付再编码流的积压，不承诺上游原始stdout历史可恢复。

【我的推断／设计】Release A的退出门：
1. 变更后的实际生产路径通过对应E3负例，旧缺陷变体必红；原T03/T04/T05回归仅为防回退，不重做历史测量。
2. 新daemon候选在获准POSIX环境完成无客户端轮询的小任务；Windows候选证明queue+held的受控边界与取消/关闭不被满队列吞没。
3. 对无法完成的Windows close/helper能力，明确提案未批准或平台未确认，不启用一个明知可能阻塞的默认cap后称“全平台生产就绪”。
4. CLI/MCP同源透传io依据；实际wheel和独立skill在获准发布验证时取得E6，未运行就不称发行已验证。

【我的推断／设计】明确不承诺：所有请求情况下固定毫秒延迟、A05/A06已经解决、任意应用业务完成ACK、通用exactly-once、Windows source-byte-exact、原生macOS等价、视频录制新格式、多个writer或多个长wait。正常用户仍能调用旧入口，新增字段/API须有批准与兼容负例。

【未确认】在A05/A06慢回包/无界接入仍存在时，Release A最多是明确局部预算与受支持负载的增量，不得宣传整个daemon内存和响应时延都已硬性有界。若owner把“全局有界”设为A版发布硬门，就必须另开≤7文件切片解决这些残余；不能用缩小措辞替代已要求的验收。

### Release B：错误完成拒绝 + 可核查恢复

【我的推断／设计】Release B聚焦 `credible-v1`：六轴一致性证据、完成依据来源、可诊断partial reply、取消与close_unconfirmed、负例拒绝、一个最小E5任务集。条件是A04基础及所需关闭/回复切片已完成；它不是另一个全功能SDK版本。

【我的推断／设计】B版退出门：`EVIDENCE_STANDARD.md`六轴在声明profile有正例与实际拒绝错误证据；对于未知上游/缺ACK不能伪造完成；正常有充分依据的任务仍能通过；新基准至少给出固定任务集的原始结果、所有失败与NOT_RUN；发行物独立验收不被源代码成功替代。

【我的推断／设计】明确不做：默认引擎替换、Rust/C重写、录制格式竞争、默认SSH/serial/KVM、独立UI框架大改、任意TUI自动DOM、未经允许的agent farm、大样本排行榜、付费服务默认调用。`cmd-art/tui-ui`保留为既有功能及fixture资产，不通过删它们制造“聚焦”的空洞收益。

## 5. 如果只能做一件事，应该是什么？

【我的推断／设计】**做出一条能在真实终端工作中拒绝“证据不足却宣告完成”的交互闭环，并把这个拒绝能力放到陌生人可运行的负例套件里。**

【我的推断／设计】理由不是“更严谨”这个形容词，而是具体失败链：T05/T04曾让观察内容或属性不可靠；T03曾将部分写入叫成功；A04会让未读积压看起来像没有新输出；ConPTY会让最后画面掩盖原始历史缺口。再强的模型也可能基于这些错误输入给出错误动作。将观察范围、输入进度和独立结果相连，直接切断这条链。[^L05][^L04][^L03][^LX2][^LX3]

【我的推断／设计】但“始终unknown、从不执行”不能赢。成对验收必须同时要求：有充分证据的有限任务能在既定预算内完成；缺证据或故意错误的任务被拒绝；两个要求任何一个失败都不能叫可信交互。比较优势只能在相同实验里体现，不使用“行业最强”作为先验。

### 首周动作：行动排序，不是工期保证

| 工作窗口 | 一项可交付物 | 做不到时的停止方式 |
|---|---|---|
| 第1工作日 | 锁定overlay与已有收据；审批A04接口/资源/关闭边界；不重跑旧实验 | 未批准的扩展保持提案，现有工作树不动 |
| 第2工作日 | W1的S1预算基础与真生产方法负例；一片最多6文件 | 自定义后端兼容无解则停，不接daemon绕过 |
| 第3工作日 | 单独S2 pending/readiness契约，再评S3 idle/busy/interleave服务 | 每片单独收据；未完成不能合并一个“基本完成” |
| 第4工作日 | W2离线证据拒绝与字段来源；关闭/回复切片只按批准范围推进 | cancel/replay未实现就UNSUPPORTED，不假绿 |
| 第5工作日 | W3固定小任务、先judge负例后模型episode；生成含缺项报告 | 凭据/平台/预算不足则NOT_RUN，不临时扩权限 |

【我的推断／设计】这张表可被本地实现难度调整，成功判据不可调整。最迟在每个工作窗口结束留下closure与下一个唯一任务；不要为了赶“第一周”把大重写或尚未验证的public API一起提交。

## 6. 对外产品句子只能在相应证据后使用

| 拟对外句子 | 最低证据条件 | 现在是否可以使用 |
|---|---|---|
| “该修复使此中文选中标签正确，且针对性回退会失败” | 附件T05 E3 | 【证据支持·E3】可以，注明作用域 |
| “该POSIX库写入调用已在真实PTY检验完整接收” | T03 E4 | 【证据支持·E4】可以，注明固定实验，不外推所有负载 |
| “无人轮询的daemon也能正确推进与应答” | 新daemon候选E4 | 【未确认】当前只有基线/原型，不可称已修 |
| “Windows捕获原始程序输出逐字节无损” | 当前profile不具备此承诺 | 【证据支持·E4】不能如此描述 |
| “五分钟可信交互套件能拒绝这六类错误” | W2新profile实际结果 | 【未确认】规格已写，未实现/未运行 |
| “优于Microsoft/agent-tty等” | 预注册同任务同权限E5对照与统计范围 | 【未确认】没有该证据，不排名 |

【我的推断／设计】Q4真正值得积累的不是更多README承诺，而是一组固定失败类、有限改动、可重复拒绝错误结果的证据资产。每次新功能必须回答：哪条失败链被阻断、哪个负例能证明、哪个平台仍没测。


---
## 来源定位

[^L03]: 附件 `SmartCLI_v3_Upload/03_receipts/T03_closure.json`，first_results、mutation_cycle、claim。E3 注入 + E4 本机 POSIX library；叙述 44 次等待。收到并阅读：2026-09-16。

[^L04]: 附件 `SmartCLI_v3_Upload/03_receipts/T04_closure.json`，evidence_scope、mutation_cycle、controls。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^L05]: 附件 `SmartCLI_v3_Upload/03_receipts/T05_closure.json`，evidence_scope、mutation_cycle、changed_files。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

[^S07]: 【证据支持·E1】[xterm.js：Flowcontrol](https://xtermjs.org/docs/guides/flowcontrol/)。E1 官方文档；输入缓冲、处理回调与背压。访问：2026-09-16。

[^S11]: 【证据支持·E1】[tmux：Control Mode](https://github.com/tmux/tmux/wiki/Control-Mode)。E1 官方文档；%begin/%end/%error 与 %output；tmux 命令结束非 shell 子命令结束。访问：2026-09-16。

[^S19]: 【证据支持·E1】[microsoft/tui-test README](https://github.com/microsoft/tui-test/blob/d7e239c49a50d13e22be81fef207e7f4f85a509a/README.md)。E1 README 声明；跨平台、多语言、四种等待、locator、录制，beta；非运行证明。访问：2026-09-16。

[^S20]: 【证据支持·E1】[microsoft/tui-test：command_settled / wait_command](https://github.com/microsoft/tui-test/blob/d7e239c49a50d13e22be81fef207e7f4f85a509a/crates/tui-test/src/engine.rs#L1981)。E1 源码；无 tracker 启动信息时退回 300ms quiet；不能外推整产品取消缺陷。访问：2026-09-16。

[^S21]: 【证据支持·E1】[coder/agent-tty README](https://github.com/coder/agent-tty/blob/ebff2c23d8273be09812d841305a4f6246ccf47e/README.md)。E1 官方仓库说明；PTY、事件日志、快照/截图/录制，参考渲染器不是原生窗口像素保证。访问：2026-09-16。

[^S22]: 【证据支持·E1】[coder/agent-tty：EventLog](https://github.com/coder/agent-tty/blob/ebff2c23d8273be09812d841305a4f6246ccf47e/src/host/eventLog.ts)。E1 源码；序号、文件权限、串行 append 和错误传播；append 不自动等于 fsync 持久化。访问：2026-09-16。

[^S23]: 【证据支持·E1】[onesuper/tui-use：Session](https://github.com/onesuper/tui-use/blob/0170481831ca57974d3c7da306c654a815e57efa/src/session.ts)。E1 源码；PTY onData→terminal.write→notifyListeners，屏幕和 scrollback。访问：2026-09-16。

[^S24]: 【证据支持·E1】[bnomei/tmux-mcp：tmux adapter](https://github.com/bnomei/tmux-mcp/blob/c4762ea36b1a288a95ba5cc125154fae65a60ad5/src/tmux.rs)。E1 源码；本地/SSH tmux 适配、并发额度和退出码 buffer。访问：2026-09-16。

[^S25]: 【证据支持·E1】[taria README](https://github.com/y0sif/taria/blob/0178e037f302cc253170f912f488157890c028e7/README.md)。E1 官方仓库说明；应用发布语义树、输入 id/ACK，需要应用配合。访问：2026-09-16。

[^S27]: 【证据支持·E1】[bnomei/tmux-mcp：README 固定快照](https://github.com/bnomei/tmux-mcp/blob/c4762ea36b1a288a95ba5cc125154fae65a60ad5/README.md)。E1 README；tracked commands、旁路退出码、tmux/支持shell依赖、会话共享；不视为本地运行证明。访问：2026-09-16。

