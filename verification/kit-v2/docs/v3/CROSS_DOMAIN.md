# CROSS_DOMAIN — 把相邻领域机制映射到 SmartCLI 的真实符号

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 0. 使用方式

【我的推断／设计】这不是采用八套框架的建议。每项只借一个可检验机制，落到一个真实失败、现存符号和失败测试。标记“拟新增”的符号尚不存在；涉及公共接口、线程、队列或默认引擎的部分只写提案，不被本文件授权。机制历史只用来解释边界，不把其他领域的安全认证转移给SmartCLI。

## 1. 浏览器自动化／CDP：操作前置条件与业务断言分离

【证据支持·E1】Playwright在动作前检查可操作条件；CDP区分键事件派发与文本插入。一个输入命令返回并不等同于页面业务目标成立，这需要额外观测／断言。[^S03][^S04]

【我的推断／设计】映射到 `PtySession.send_keys`、`send_text`、`_resolve_key` 与 `tui._handle`：先消费已知输入前的输出，确认当前generation、geometry revision与模式，再编码输入；传输返回只说明写入层，任务谓词由后续wait/独立judge判断。特别是SS3/CSI选择读取 `model.app_cursor`，不能用旧屏幕模式编码后再宣称按键送达。[^S17]

【我的推断／设计】可选提案 `act_if_revision(expected_generation, expected_geometry, input)` 仅拒绝已知过期状态，不承诺程序内部状态不会同时变化。外部TUI没有浏览器DOM可操作性树，不能伪造 `enabled=true` 或 `focused=true`。只知道反色，就报告反色观察或候选选中项。

【我的推断／设计】测试 `test_key_uses_committed_mode`：在输入前向真实ScreenModel馈入DECCKM变化，确认编码随模式而变；测试 `test_stale_geometry_refused`：旧geometry引用不能在resize后继续动作；测试 `test_written_is_not_goal_complete`：目标无响应，write成功也不能产出业务PASS。这些是新的边界测试，不重跑T05旧复现。原生不同应用对模式的真实兼容性仍 `NOT_RUN`。

## 2. 数据库WAL／checkpoint：固定读边界与可重建状态

【证据支持·E1】SQLite WAL使用追加日志与提交标记，读者使用固定的日志边界，checkpoint将已提交内容并回数据库。该机制提供的是数据库内部事务语义。[^S05]

【我的推断／设计】映射到 `PtySession.pump` 的read→feed、`ScreenModel`、`_ByteStream._state/_csi` 与 `tui._snapshot_response`：记录delivered offset，当轮feed返回后发布frame revision，并记录已交给parser的fed_offset；观察者只读同一已发布revision，不在读取时分别清除dirty或消费transport。将“已观察”和“已持久化”分别记录，避免日志写失败仍称可完整重放。

【我的推断／设计】没有必要先引入SQLite。可先使用短JSONL trace与完整初始条件，事件涵盖输入、输出、resize、EOF及parse error；拟议checkpoint只保存可版本化数据，不使用反序列化可执行对象。`visual_hash()`目前会消费dirty状态，不能让多个observer竞相调用它作为独立提交器。[^LCS]

【我的推断／设计】最关键的反例是：只保存画面却丢掉半个 `ESC[38:2::...` 的parser状态，恢复后屏幕文字可能正确而后续样式错误。测试 `test_checkpoint_inside_sgr_or_utf8` 应在半序列处切断，再恢复与不切断结果比较；测试 `test_replay_rejects_gap` 删除中间event必须拒绝连续性主张；若没有完整checkpoint机制，先只支持从已知初始状态短trace重放。

【我的推断／设计】数据库“提交”不能与外部PTY写入原子绑定。若进程在“字节已写、日志未落盘”之间崩溃，日志无法证明是否重发安全。必须记录 `delivery_unknown` 并禁止自动整包重试；不能借用WAL这个词承诺终端exactly-once。ConPTY replay复现的是捕获的重构流，不是子进程原始写历史。[^LX2]

## 3. OS调度与背压：按工作量公平让步，不按请求数量自欺

【证据支持·E1】Linux CFS设计材料以虚拟运行时间解释公平分配；xterm.js流控指南区分写入排队与实际消费，并以高低水位调节流量。这里借的是调度与背压机制，不声称当前Linux默认调度器仍等于历史CFS设计。[^S06][^S07]

【我的推断／设计】映射到 `tui._serve_forever.worker`、`_drain_interleavable`、`PtySession.pump`、两个backend的 `read_nonblocking`：每轮共享byte/job/scan预算，在空闲、请求之间和长wait poll gap都能推进I/O。一个snapshot不能重新获得整轮byte预算；请求洪泛也不能把I/O挤到“只有queue.Empty才处理”。

【我的推断／设计】不要只加 `max_jobs=8`：单个snapshot可能解析巨大积压、单个reply可能阻塞60秒、同步write可能等待可写。字节、解析切片、扫描条目与输出发送分别计量。预算只提供合作式边界，不能抢占一个已经阻塞的Python/native调用。A05/A06未修时，禁止宣传端到端实时性。[^LCD][^LCB]

【我的推断／设计】测试 `test_busy_queue_still_services_io` 持续提供快请求但每轮I/O仍前进；`test_one_budget_across_nested_snapshot` 验证嵌套快请求不能重置预算；`test_read_cap_smaller_than_observed_pty_backpressure` 在注入transport上以小于12KiB的read quantum反复推进，证明“单次预算必须大于12KiB”不是必要条件。最后一项是设计反例，不重跑X3。[^LX3]

【我的推断／设计】Windows的cap应以重编码payload字节加item数量约束，同时记录reader-held suffix和consumer暂存。把无界队列改成有界队列，控制的是这层内存/reader推进，不保证ConPTY上游向子进程传递精确背压。原生RSS、总积压与吞吐仍需新的候选验收，不从参考模型推导。[^LX2]

## 4. Unicode UAX#29／#11：字符边界、显示宽度与终端地址不是一件事

【证据支持·E1】UAX#29定义默认grapheme等文本边界；UAX#11明示East_Asian_Width不是无需定制即可用于所有现代终端的列宽方案。两份规范不能直接给出当前终端每个glyph占几列的通用答案。[^S08][^S09]

【证据支持·E3】T05已将高亮span按cell聚合，避免以Python字符串下标解释终端列；T04已正确保留跨feed的过滤器状态。这里不重新判断它们是否修好。[^L05][^L04]

【我的推断／设计】映射到 `build_snapshot`、`ScreenModel.row_cells/display`、`_Screen.draw` 与截图工具的cell布局：坐标域固定为cell，内容域保留Unicode原样；grapheme分段只用于描述或输入编辑策略，不能再拿grapheme数当cell数。T05是内联cell聚合实现，本包不假定存在 `_cell_span_text` 函数。[^LCP][^LCS]

【我的推断／设计】新增观察profile记录pyte/wcwidth版本、列宽策略、TERM/locale、尺寸；原始输入不做隐式NFC/NFKC规范化，不将规范化后的hash冒充原字节hash。对无法证明的ZWJ/ambiguous-width情况返回profile限制，而不是通过改变标签使其看起来对齐。

【我的推断／设计】测试 `test_span_cell_domain_with_combining_and_stub` 覆盖base+组合标记、宽字符续格、左右边界；`test_width_profile_mismatch_refuses_pixel_claim` 用相同文本、不同宽度profile拒绝“像素一致”的证据。仅按当前model验证的结果是E3；不同实际terminal的渲染一致性仍未测，不因为符合UAX就写“所有终端兼容”。

## 5. Kitty keyboard protocol：协商真实能力，不发送猜测的增强键码

【证据支持·E1】Kitty键盘协议定义可查询与逐步启用的能力标志，包含键事件类型和状态push/pop；主屏与备屏相关状态需要按协议处理。支持一种编码不等于支持全部增强选项。[^S10]

【我的推断／设计】映射到 `_resolve_key`、`PtySession.send_keys`、`ScreenModel`的模式处理和 `drain_replies`。先保留现有CSI/SS3；拟新增能力记录只在实现对应编码与模式状态后才允许响应。不能向应用宣告Kitty支持，却仍用旧键表发送所有输入。输入transport写完不是应用识别该协议的确认。

【我的推断／设计】第一步不是实现整套协议，而是建立 `test_unadvertised_protocol_stays_legacy` 与 `test_keyboard_mode_restored_after_alt_screen` 的fixture规格，离线枚举query、enable、push/pop、非法flag与未知序列。若未来只实现某一flag，测试应验证其余flag不被宣传。未知组合键返回可诊断错误，不静默当成要输入的字符串；该行为改变属于公共输入契约，需批准。

【未确认】当前SmartCLI对Kitty增强模式的完整支持没有附件证明；不得标“已支持”。原生键盘、应用协商、Windows重编码及鼠标混合场景都需要本地验证。该方向不阻塞A04的持续消费修复。

## 6. tmux control mode：控制请求回执与被控程序输出分流

【证据支持·E1】tmux control mode使用带编号的begin/end/error区分控制命令结果，并通过output通知发送pane输出；输出包含需要解码的转义形式。tmux自身某些模式界面不在普通pane输出通道中。[^S11]

【我的推断／设计】映射到 `tui._send_request/_call/_reply` 与未来可选tmux adapter：控制plane请求ID、输入action ID、screen revision、子进程退出依据分别记录。一个“send-keys命令执行成功”的control回执，只能证明tmux处理了该控制命令，不能证明pane中的shell命令完成或Vim保存成功。

【我的推断／设计】测试 `test_control_ack_is_not_child_completion`：成功control reply后pane没有变化，任务不得完成；`test_control_frames_split_and_interleaved`：把begin/output/end跨任意片分发，仍关联正确请求，拒绝编号错配；`test_octal_output_decoder_preserves_bytes`：包含反斜杠、控制码和跨片UTF-8，不能先错误解码再丢掉原字节。

【我的推断／设计】默认运行时不转成tmux依赖。需要复用现有tmux会话时做独立可选适配，保留窗口/复制模式观察限制；Windows原生能力不能因这个适配被删除。该功能不在本轮A04生产第一切片里。

## 7. 结构化可观测性：发生、被观察、被解释，时间与来源分离

【证据支持·E1】OpenTelemetry日志数据模型区分源事件Timestamp与采集ObservedTimestamp，并可关联TraceId/SpanId。模型没有要求每个事件一定知道源发生时间。[^S12]

【我的推断／设计】映射到 `WinptyBackend._read_loop`、`PosixPtyBackend.read_nonblocking`、`PtySession.pump`、`_snapshot_response`、MCP返回及独立judge：分别记录reader获取、owner解析、调用返回与judge确认的本地单调时间；有意义时添加wall-clock用于跨文件关联。ConPTY批量投递时，读到一批的时间不能冒充子进程生成每条输出的时间。[^LX2]

【我的推断／设计】拟新增轻量事件字段 `observed_at_monotonic`、`fed_at_monotonic`、`origin`、`generation`、`action_id`、`local_cut`。不引入OpenTelemetry SDK或后台exporter；先在现有JSON响应与测试receipt验证必要字段。若没有子进程时钟，`source_timestamp=null`。日志默认不记录输入秘密和环境变量值，敏感payload是否保存需显式选择。

【我的推断／设计】测试 `test_delayed_delivery_does_not_invent_source_time`：延迟一次poll只改变ObservedTimestamp，不产生伪源时间；`test_adapter_basis_never_becomes_runtime_basis`：旧conformance自己推定MARKER时，输出origin必须仍为harness；`test_clock_step_does_not_reorder_events`：wall-clock倒退不影响单调序号与deadline。

【我的推断／设计】日志数量不是收益。收益判据是能否区分“上游尚未投递”“owner尚未消费”“解析失败”“RPC回包慢”。至少两个不同故障若仍生成同样的`timeout`信息，这次字段扩展就没有完成诊断目标。

## 8. 航天与航空：检测执行链是否活着，明确哪些响应没有关闭任务

【证据支持·E1】NASA F Prime的Health组件向被监控组件发送带key的ping，要求响应在该组件自身线程处理，由此检查执行链。FAA CPDLC材料把STANDBY与关闭对话的响应区分；例如WILCO是接受/将遵从的响应语义，不是物理动作已经完成的证明。[^S13][^S14]

【我的推断／设计】第一条映射到 `tui._serve_forever.worker/_drain_interleavable`：accept thread仍在接受连接不等于screen owner仍在推进。拟新增只读health信息应反映最后owner服务轮次、已解析seq、待处理输入/回复和阻塞原因，不由无关线程每秒自增一个计数就宣布健康。

【我的推断／设计】第二条映射到 `cmd_close`、`PtySession.close`、backend `terminate` 与wait结果：`close_requested` 相当于请求已受理，`close_unconfirmed` 相当于尚未形成闭环；只有获得规定退出/EOF条件才可报告closed_confirmed。即使协议对话关闭，也仍需独立业务验证。保留registry及诊断句柄，不用删除文件制造“零会话”的假象。[^LCD][^LCB]

【我的推断／设计】测试 `test_accept_alive_owner_stalled_health_not_green` 注入owner停滞，accept仍活也不能报告正常推进；`test_cancel_ack_does_not_confirm_exit` 注入取消响应但进程未退出；`test_close_timeout_keeps_generation_and_handles` 验证未确认关闭仍能恢复定位。故障隔离限定在受影响会话或observer，不能一个日志写失败就杀死全部用户会话。

【我的推断／设计】不照搬航空响应词当SmartCLI公共API，也不声称达到航空/航天可靠性认证。借鉴的只有：状态由证据推进、检测真正的执行路径、失败影响范围明确。实际健康阈值与Windows关闭收敛仍需要候选实现验证，不能从NASA设计推出本机时延。

## 9. 首轮能落地的最小组合

【我的推断／设计】A04第一轮仅采用三条交叉机制：调度的共享预算、观测时间/来源分离、状态机的未确认终局。W2采用浏览器式“动作与断言分离”及证据固定边界。WAL完整checkpoint、Kitty协商、tmux adapter只做后续提案。这样每一项都能对应一个已知失败，而不是为了机制完整性扩增模块。

【未确认】本文件的新增测试均为可实现规格，本轮未运行。外部协议说明是E1，不能替代SmartCLI E3/E4；E3/E4也不能自动转为端到端任务E5或发行验证E6。


---
## 来源定位

[^L04]: 附件 `SmartCLI_v3_Upload/03_receipts/T04_closure.json`，evidence_scope、mutation_cycle、controls。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^L05]: 附件 `SmartCLI_v3_Upload/03_receipts/T05_closure.json`，evidence_scope、mutation_cycle、changed_files。E3，已复核；不要求重跑原实验。收到并阅读：2026-09-16。

[^LCB]: 附件 `SmartCLI_v3_Upload/04_code/pty_backend.py_T03_implemented.py`，PtyBackend、WinptyBackend._read_loop/read_nonblocking/terminate、PosixPtyBackend.write。E1 本轮实现源码，T03 已落地；不以远端旧代码覆盖。收到并阅读：2026-09-16。

[^LCD]: 附件 `SmartCLI_v3_Upload/04_code/tui.py_CURRENT_daemon_A04_target.py`，_serve_forever、worker、INTERLEAVE_OK、_drain_interleavable、_reply、_snapshot_response、cmd_close。E1 当前 daemon 源码；既有 interleave/resize 排除必须保留。收到并阅读：2026-09-16。

[^LCP]: 附件 `SmartCLI_v3_Upload/04_code/snapshot.py_T05_implemented.py`，build_snapshot：menu_items 的 cell 聚合。E1 本轮实现源码，T05 已落地；没有假设存在独立 _cell_span_text 函数。收到并阅读：2026-09-16。

[^LCS]: 附件 `SmartCLI_v3_Upload/04_code/screen_model.py_T04_implemented.py`，_ByteStream.feed/_state、ScreenModel.feed/drain_replies/visual_hash。E1 本轮实现源码，T04 已落地。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

[^S03]: 【证据支持·E1】[Playwright：Auto-waiting](https://playwright.dev/docs/actionability)。E1 官方文档；操作前可操作性检查与结果断言是不同机制。访问：2026-09-16。

[^S04]: 【证据支持·E1】[Chrome DevTools Protocol：Input.pdl](https://github.com/ChromeDevTools/devtools-protocol/blob/acf4480d3e16cc3043edd87837726e10d3fe4f2a/pdl/domains/Input.pdl)。E1 源码/协议；dispatchKeyEvent、insertText；固定提交，不宣称是未来最新版本。访问：2026-09-16。

[^S05]: 【证据支持·E1】[SQLite：Write-Ahead Logging](https://sqlite.org/wal.html)。E1 官方文档 §2–2.2；commit、checkpoint、reader end mark。访问：2026-09-16。

[^S06]: 【证据支持·E1】[Linux kernel：CFS Scheduler](https://docs.kernel.org/scheduler/sched-design-CFS.html)。E1 官方设计文档；借鉴按实际服务量记账，不声称 CFS 是当前唯一默认调度器。访问：2026-09-16。

[^S07]: 【证据支持·E1】[xterm.js：Flowcontrol](https://xtermjs.org/docs/guides/flowcontrol/)。E1 官方文档；输入缓冲、处理回调与背压。访问：2026-09-16。

[^S08]: 【证据支持·E1】[Unicode UAX #29：Unicode Text Segmentation](https://unicode.org/reports/tr29/)。E1 规范；字素边界不等于 glyph 或终端列宽。访问：2026-09-16。

[^S09]: 【证据支持·E1】[Unicode UAX #11：East Asian Width](https://unicode.org/reports/tr11/)。E1 规范；现代终端需 tailoring，不是现成通用列宽算法。访问：2026-09-16。

[^S10]: 【证据支持·E1】[Kitty：Comprehensive keyboard handling in terminals](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)。E1 官方协议；协商、事件类型、主/备屏独立键盘模式栈。访问：2026-09-16。

[^S11]: 【证据支持·E1】[tmux：Control Mode](https://github.com/tmux/tmux/wiki/Control-Mode)。E1 官方文档；%begin/%end/%error 与 %output；tmux 命令结束非 shell 子命令结束。访问：2026-09-16。

[^S12]: 【证据支持·E1】[OpenTelemetry：Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)。E1 规范；Timestamp、ObservedTimestamp、TraceId、SpanId。访问：2026-09-16。

[^S13]: 【证据支持·E1】[NASA/JPL F Prime：Svc::Health](https://fprime.jpl.nasa.gov/latest/Svc/Health/docs/sdd/)。E1 官方组件设计 §2、3.2.1、6；在受监测组件自身线程回应 ping 与超时。访问：2026-09-16。

[^S14]: 【证据支持·E1】[FAA：JO 7110.65 Chapter 14 Section 2，CPDLC](https://www.faa.gov/air_traffic/publications/atpubs/atc_html/chap14_section_2.html)。E1 官方程序；TBL 14-2-1，WILCO/UNABLE 等关闭消息，STANDBY 不是完成。访问：2026-09-16。

[^S17]: 【证据支持·E1】[SmartCLI：PtySession（基线未改模块）](https://github.com/dwgx/SmartCLI/blob/701e61f6d69aa2420617edf80b1136df8d5e8cf7/smartcli_core/session.py)。E1 源码；pump read→feed→reply，send_line 分两次写；不取代附件中三个已修改模块。访问：2026-09-16。

