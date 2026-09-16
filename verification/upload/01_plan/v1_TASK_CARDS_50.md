# 本地可实施的50项任务卡

前38项沿用旧审计，全部从pending开始；新增12项补齐规范、执行和研究边界。任务不是同一release范围。依赖可在ADR中重新设计；不要悄悄绕过。

## T01 · 锁定代码、依赖、测试执行清单
优先级：P0；初始依赖：无；范围：G0 基线与回归。
源码入口/资产：`tests/；tools/；docs/`

**任务意图与起手工作**
记录HEAD、tree、Python、pyte、ConPTY、TERM及pytest/脚本入口；生成test manifest，维护first-pass与rerun字段。

**验收门槛**
源树与wheel分别跑；所有skip注明原因；不从历史文档推断绿灯。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC10](12_SOURCES.md#sc10) [SC11](12_SOURCES.md#sc11) [SC12](12_SOURCES.md#sc12)

## T02 · 添加短写、分片、列坐标回归
优先级：P0；初始依赖：T01；范围：G0 基线与回归。
源码入口/资产：`tests/test_audit_regressions.py`

**任务意图与起手工作**
先接入交付测试草案并确认原版本失败；逐个最小化，避免把实现细节变公共契约。

**验收门槛**
三个错误路径在原版本红、修复后绿；故意还原bug仍红。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03) [SC05](12_SOURCES.md#sc05) [SC06](12_SOURCES.md#sc06)

## T03 · 有界write_all与输入完成状态
优先级：P0；初始依赖：T02；范围：G1 核心正确性。
源码入口/资产：`smartcli_core/pty_backend.py；session.py`

**任务意图与起手工作**
维护offset；EAGAIN可写通知；deadline/cancel；InputReceipt accepted/written分离。

**验收门槛**
长文本byte-exact、EINTR不丢、没有无界busyloop。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03) [STD01](12_SOURCES.md#std01)

## T04 · 流式SGR与分片不变性
优先级：P0；初始依赖：T02；范围：G1 核心正确性。
源码入口/资产：`smartcli_core/screen_model.py`

**任务意图与起手工作**
控制序列跨feed保留；正确subparams；长未终止序列有界；损坏序列恢复明确。

**验收门槛**
所有切分点及随机切分得到等价supported cells。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC05](12_SOURCES.md#sc05)

## T05 · 统一cell span文字提取
优先级：P0；初始依赖：T02；范围：G1 核心正确性。
源码入口/资产：`snapshot.py；screen_model.py`

**任务意图与起手工作**
cell_span_text作为唯一坐标转换；wide continuation与grapheme示例；复用到PNG/locators。

**验收门槛**
中文 OK、日文、重音、ZWJ与右边界测试；不靠len(text)定义终端列。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC05](12_SOURCES.md#sc05) [SC06](12_SOURCES.md#sc06) [SC14](12_SOURCES.md#sc14)

## T06 · 修正构建依赖下限
优先级：P1；初始依赖：T01；范围：G1 核心正确性。
源码入口/资产：`pyproject.toml；CI package`

**任务意图与起手工作**
setuptools下限提升到确认支持PEP639的版本；最低依赖构建测试。

**验收门槛**
低于要求版本不被resolver选中；最低允许版本build/twine均通过。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC02](12_SOURCES.md#sc02) [STD02](12_SOURCES.md#std02)

## T07 · 单owner循环持续drain
优先级：P0；初始依赖：T03, T04, T05；范围：G2 有界会话运行时。
源码入口/资产：`smartcli_core/session.py；tui.py`

**任务意图与起手工作**
OwnerLoop接收IO/events/requests；每tick字节与CPU预算；模型只在owner更新。

**验收门槛**
无人轮询时子进程正常推进；CPR被及时回答；busy output可响应cancel。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03) [SC04](12_SOURCES.md#sc04) [SC08](12_SOURCES.md#sc08) [CP09](12_SOURCES.md#cp09)

## T08 · 认证前与认证后资源配额
优先级：P0；初始依赖：T01；范围：G2 有界会话运行时。
源码入口/资产：`tui.py :: reader/accept/jobs`

**任务意图与起手工作**
有界reader池/信号量、请求字节/连接率/queue长度；busy错误可重试且不泄漏screen。

**验收门槛**
caps设小值做确定性测试，活跃线程和queue永不突破。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC08](12_SOURCES.md#sc08)

## T09 · 把写回响应移出模型owner
优先级：P0；初始依赖：T07, T08；范围：G2 有界会话运行时。
源码入口/资产：`tui.py :: _reply`

**任务意图与起手工作**
每连接有限输出缓冲/截止；IO线程或selector负责socket，owner不sendall。

**验收门槛**
慢读者/断开连接不拖慢其他请求；有界response内存。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC08](12_SOURCES.md#sc08)

## T10 · 多个watcher与优先cancel
优先级：P1；初始依赖：T07, T09；范围：G2 有界会话运行时。
源码入口/资产：`readiness.py；tui.py`

**任务意图与起手工作**
将阻塞wait改为注册predicate；单owner对revision广播；每watcher独立deadline/cancel。

**验收门槛**
3个watcher同时工作；一个取消不动其它；close不会等待60秒旧wait。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC07](12_SOURCES.md#sc07) [SC08](12_SOURCES.md#sc08) [SC13](12_SOURCES.md#sc13)

## T11 · 缓存ExitState与启动资源事务
优先级：P1；初始依赖：T07；范围：G2 有界会话运行时。
源码入口/资产：`pty_backend.py；tui.py lifecycle`

**任务意图与起手工作**
waitpid单处消费并缓存exit；spawn/registry失败finally覆盖；PID+startidentity；Windows队列绑定旧proc并join。

**验收门槛**
exit7持久可查询；startup failure不留PTY；重用backend不串旧数据。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03) [SC08](12_SOURCES.md#sc08)

## T12 · 进程树和会话限额治理
优先级：P1；初始依赖：T08, T11；范围：G2 有界会话运行时。
源码入口/资产：`pty_backend.py；tui.py`

**任务意图与起手工作**
进程组/Job对象可选containment；idle TTL与保留期；容量预约原子化；GC先确认死亡。

**验收门槛**
受控子孙被清理；逃逸策略明确；并发start不突破cap；不得盲删活token。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03) [SC08](12_SOURCES.md#sc08) [SC13](12_SOURCES.md#sc13)

## T13 · 版本化请求响应与capabilities
优先级：P1；初始依赖：T07；范围：G3 可信协议。
源码入口/资产：`smartcli_core/protocol.py(新增)；drive adapters`

**任务意图与起手工作**
定义v2 envelope、错误码、deadline、capabilities、engine/profile/version；消除内部JSON嵌套字符串。

**验收门槛**
CLI/MCP/Python黄金响应一致；未知能力返回unsupported；v1仍可用。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC08](12_SOURCES.md#sc08) [SC09](12_SOURCES.md#sc09) [CP01](12_SOURCES.md#cp01)

## T14 · action_id/seq/epoch与原子act
优先级：P1；初始依赖：T10, T13；范围：G3 可信协议。
源码入口/资产：`session.py；新protocol/observations`

**任务意图与起手工作**
按事件递增seq、screen_revision、geometry_epoch；先比expected_seq，再write，再注册after_seq predicate。

**验收门槛**
旧screen/action、其他writer/resize不能伪证本动作；相同画面再现也有不同seq。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC04](12_SOURCES.md#sc04) [SC08](12_SOURCES.md#sc08) [CP06](12_SOURCES.md#cp06) [CP19](12_SOURCES.md#cp19)

## T15 · writer lease与read-only能力
优先级：P1；初始依赖：T13, T14；范围：G3 可信协议。
源码入口/资产：`tui.py；policy.py(新增)`

**任务意图与起手工作**
观察与输入token分离；writer lease带expiry/fencing；同UID不是沙箱；human takeover可撤销。

**验收门槛**
过期/旧fencing写入失败；readonly可watch不可type；并发不交错输入。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC08](12_SOURCES.md#sc08) [SC09](12_SOURCES.md#sc09) [CP16](12_SOURCES.md#cp16)

## T16 · 显式等待与命令边界
优先级：P1；初始依赖：T10, T11, T14；范围：G3 可信协议。
源码入口/资产：`session.py；readiness.py；shell adapters`

**任务意图与起手工作**
新增wait_idle/wait_exit/wait_command；command支持shell hook或可信sidechannel，不通用屏幕猜测；任意TUI返回unsupported。

**验收门槛**
shell command exit0/7正确；TUI idle不声称完成；marker若只匹配旧内容不产生新command verdict。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP03](12_SOURCES.md#cp03) [CP12](12_SOURCES.md#cp12) [CP13](12_SOURCES.md#cp13) [SC07](12_SOURCES.md#sc07)

## T17 · 脚本assert与失败退出码
优先级：P1；初始依赖：T13, T16；范围：G3 可信协议。
源码入口/资产：`tui.py :: _run_steps；CLI formatter`

**任务意图与起手工作**
添加strict脚本模式、步骤ID、assert_text/assert_state、失败证据；保留旧模式显式迁移。

**验收门槛**
超时失败返回非零且step原因完整；错误码稳定；测试框架可直接使用。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC08](12_SOURCES.md#sc08) [CP03](12_SOURCES.md#cp03)

## T18 · 不确定感知与降级状态
优先级：P1；初始依赖：T05, T13；范围：G3 可信协议。
源码入口/资产：`snapshot.py；protocol.py`

**任务意图与起手工作**
保留raw事实，语义推断注明来源与candidate/confidence；feed_errors/dropped/bufferlag进入fidelity。

**验收门槛**
theme误选能够abstain；退化状态不被ok覆盖；红色不自动当命令失败。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC05](12_SOURCES.md#sc05) [SC06](12_SOURCES.md#sc06) [SC16](12_SOURCES.md#sc16)

## T19 · MCP风险提示、secret通道与沙箱策略
优先级：P1；初始依赖：T13, T15；范围：G3 可信协议。
源码入口/资产：`mcp_server.py；policy.py`

**任务意图与起手工作**
保守annotations；env通过受控IPC而非argv；默认不记录secret；提供可选sandbox adapter不伪装默认隔离。

**验收门槛**
ps/log/report无fake secret；危险能力可拒绝；prompt injection正文始终作为不可信数据。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC09](12_SOURCES.md#sc09) [STD03](12_SOURCES.md#std03) [STD04](12_SOURCES.md#std04)

## T20 · 区域/差分/scrollback与reader游标
优先级：P2；初始依赖：T14, T18；范围：G4 低成本观察与输入。
源码入口/资产：`observations.py(新增)；screen_model.py`

**任务意图与起手工作**
session内一个日志，reader各持since_seq；full/region/diff modes；超出保留期返回resync_required。

**验收门槛**
两个reader读互不消费；resize显式resync；token预算截断字段可见。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP09](12_SOURCES.md#cp09) [CP25](12_SOURCES.md#cp25) [CP26](12_SOURCES.md#cp26)

## T21 · 模式感知键、粘贴与鼠标
优先级：P2；初始依赖：T03, T13；范围：G4 低成本观察与输入。
源码入口/资产：`session.py；input.py(新增)`

**任务意图与起手工作**
KeySpec严格校验；DECCKM保持；paste/bracketed/mouse reporting模式；修饰键表与能力协商。

**验收门槛**
每种模式在真实ncurses/Vim/菜单上验证；错误键不输入字面串。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC04](12_SOURCES.md#sc04) [CP01](12_SOURCES.md#cp01) [CP21](12_SOURCES.md#cp21)

## T22 · 稳态判定区域化/事件化
优先级：P2；初始依赖：T10, T20；范围：G4 低成本观察与输入。
源码入口/资产：`readiness.py；observations.py`

**任务意图与起手工作**
idle区分transport/content/visual；可忽略已声明动画region但不静默忽略selection。

**验收门槛**
spinner不阻止等待另一region；选择移动必触发visual；deadline含所有工作耗时。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC07](12_SOURCES.md#sc07) [CP08](12_SOURCES.md#cp08)

## T23 · 可选终端引擎契约和profile
优先级：P2；初始依赖：T04, T05, T18；范围：G4 低成本观察与输入。
源码入口/资产：`screen_model.py；engines/`

**任务意图与起手工作**
抽象feed/frame/modes/replies/resize，pyte先实现；按证据选择xterm/Ghostty旁路实验，不默认迁移。

**验收门槛**
现有fidelity回归全保留；IL/DL差异按profile，不把tmux投票当标准。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC05](12_SOURCES.md#sc05) [CP01](12_SOURCES.md#cp01) [CP09](12_SOURCES.md#cp09)

## T24 · 追加事件日志与checkpoint
优先级：P2；初始依赖：T11, T14, T19；范围：G5 证据与协作。
源码入口/资产：`recording.py(新增)`

**任务意图与起手工作**
schema/seq/monotonic ts记录输出/输入/resize/exit；write失败导致recording_degraded；设磁盘限额。

**验收门槛**
重放同engine/version/profile得到同cells；存储满时不伪造完整记录；原始内容保留策略明确。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP06](12_SOURCES.md#cp06) [CP07](12_SOURCES.md#cp07)

## T25 · 复用截图工具接入持久session
优先级：P2；初始依赖：T18, T24；范围：G5 证据与协作。
源码入口/资产：`tools/screenshot/shot.py；drive API`

**任务意图与起手工作**
接immutable frame，而非再spawn；固定字体/宽度profile元数据；PNG作为可选extra；再考虑cast/video。

**验收门槛**
capture对应确切seq；包内不分享字体文件；清楚标注reference renderer而非宿主真实截图。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC14](12_SOURCES.md#sc14) [SC15](12_SOURCES.md#sc15) [CP07](12_SOURCES.md#cp07) [CP21](12_SOURCES.md#cp21)

## T26 · 故障proof bundle与重放入口
优先级：P2；初始依赖：T17, T24, T25；范围：G5 证据与协作。
源码入口/资产：`artifacts/；CLI；MCP resources`

**任务意图与起手工作**
输出manifest、事件片段、前后snapshot、PNG、动作及独立assert；可通过资源URI读取。

**验收门槛**
离线另一个人能重演观察和检查断言；仅成功文本不能当证明。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP06](12_SOURCES.md#cp06) [CP07](12_SOURCES.md#cp07)

## T27 · 人类只读attach与受控接管
优先级：P2；初始依赖：T15, T20, T24；范围：G5 证据与协作。
源码入口/资产：`attach viewer；policy`

**任务意图与起手工作**
先readonly镜像，再接管lease；人接管导致agent fenced；同会话状态保留。

**验收门槛**
接管/返还/掉线均不交错按键；kill监督与子进程真实退出分开。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP15](12_SOURCES.md#cp15) [CP16](12_SOURCES.md#cp16) [CP22](12_SOURCES.md#cp22)

## T28 · SemanticProvider与tui-ui试点
优先级：P3；初始依赖：T14, T18, T21；范围：G6 可选语义适配。
源码入口/资产：`adapters/semantics.py；skills/tui-ui`

**任务意图与起手工作**
定义app-provided vs inferred来源；widget ID、focus、actions、revision、ACK；先适配自己的UI做可验证纵切。

**验收门槛**
同应用黑盒和语义模式任务等价；应用IGNORED与未确认可分；不谎称任意TUI有tree。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP18](12_SOURCES.md#cp18) [CP19](12_SOURCES.md#cp19) [CP20](12_SOURCES.md#cp20)

## T29 · Neovim/Textual/taria桥
优先级：P3；初始依赖：T28；范围：G6 可选语义适配。
源码入口/资产：`adapters/nvim.py；adapters/textual.py；adapters/taria.py`

**任务意图与起手工作**
各适配独立extras；RPC读取mode/buffer作应用增强；协议不支持直接回退cells；隔离许可/依赖。

**验收门槛**
strict-UI赛道不得偷偷用RPC改文件；语义赛道明示使用；版本兼容与权限测试。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP18](12_SOURCES.md#cp18) [CP24](12_SOURCES.md#cp24)

## T30 · 远程会话传输作为独立后端
优先级：P3；初始依赖：T11, T15, T24；范围：G6 可选语义适配。
源码入口/资产：`transports/ssh.py(可选)`

**任务意图与起手工作**
本地SSH PTY保留screen engine；断线/重连标记，不承诺恢复已死进程；串口/3270以后需求再立项。

**验收门槛**
断线不能成功回ACK；远程hostkey与凭证由受控配置，不自动跳过验证。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC03](12_SOURCES.md#sc03)

## T31 · 三赛道统一基准与独立裁判
优先级：P1；初始依赖：T01；范围：G7 可比较评测。
源码入口/资产：`benchmarks/；existing Harbor adapter`

**任务意图与起手工作**
strict UI / adapted / mixed三赛道；固定模型/任务/预算，提取过程指标与最终独立assert；为每工具写同能力adapter。

**验收门槛**
禁止sed绕过Vim算成功；未知结果fail或unknown不算pass；报告全部失败/skip。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC10](12_SOURCES.md#sc10) [CP05](12_SOURCES.md#cp05)

## T32 · 故障注入/差分/Unicode语料
优先级：P2；初始依赖：T02, T07, T18；范围：G7 可比较评测。
源码入口/资产：`tests/terminal_corpus；tools/screenshot/perception_matrix.py`

**任务意图与起手工作**
片段随机化、宽度profile、CPU/load、断开慢读、device query、现代TUIs，固定seed保存最小repro。

**验收门槛**
参考终端分歧标注；已知版本变动不偷偷删golden；本机fake攻击边界。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC05](12_SOURCES.md#sc05) [SC16](12_SOURCES.md#sc16)

## T33 · 效能与成本实测仪表
优先级：P2；初始依赖：T20, T31, T32；范围：G7 可比较评测。
源码入口/资产：`benchmarks/reporter.py`

**任务意图与起手工作**
success/firstpass/median/p95/tokens/calls/RSS/recovery；机器性能固定；区分boot成本与持续session成本。

**验收门槛**
给出样本量与不确定区间；无测量不写更快/省xx%；新增feature不提升空泛总分替代结果。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[CP01](12_SOURCES.md#cp01) [CP06](12_SOURCES.md#cp06)

## T34 · 测试manifest进CI，第一轮失败不可隐藏
优先级：P1；初始依赖：T01, T02, T06；范围：G8 发布与生态。
源码入口/资产：`ci.yml；tests/run_all.py`

**任务意图与起手工作**
所有关键runtime/perception测试映射到OSmatrix；retry保留第一次结果；package源/轮子执行同契约。

**验收门槛**
新A01–A06门禁在适用OS可执行；每个skip有reason；无需重启Dependabot版本PR。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC10](12_SOURCES.md#sc10) [SC11](12_SOURCES.md#sc11) [SC17](12_SOURCES.md#sc17)

## T35 · README与可复現演示重构
优先级：P2；初始依赖：T17, T25, T26；范围：G8 发布与生态。
源码入口/资产：`README*；docs/site；examples`

**任务意图与起手工作**
首屏Agent terminal runtime；Vim/菜单/后台任务三demo；已有art/UI作为支持模块与测试资产；前后证据链接。

**验收门槛**
按copy-paste路径检查Linux/Win/mac；不重复承诺已经存在的MCP/PyPI。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC01](12_SOURCES.md#sc01) [SC02](12_SOURCES.md#sc02) [SC12](12_SOURCES.md#sc12)

## T36 · 维护者/AI交接、元数据单一来源
优先级：P2；初始依赖：T13, T34；范围：G8 发布与生态。
源码入口/资产：`HANDOFF.md；NEXT-STEPS.md；tools/sync_vendor.py`

**任务意图与起手工作**
current baseline由代码生成；历史附录不可冒充当前；版本10点与vendor仍由门禁验证；逐PR可回滚。

**验收门槛**
继任者可依据ID/sha/source/test复工，不靠聊天历史；不打包被排除资料。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC11](12_SOURCES.md#sc11) [SC12](12_SOURCES.md#sc12) [SC13](12_SOURCES.md#sc13)

## T37 · 分发依赖、许可和安全发布门
优先级：P2；初始依赖：T06, T24, T34, T36；范围：G8 发布与生态。
源码入口/资产：`pyproject；publish；NOTICE/SBOM`

**任务意图与起手工作**
pin审查借鉴commit/许可；复用设计优先、拷贝代码前核license；最小extras；手动安全升级评估和发布证明。

**验收门槛**
wheel/sdist/skills三产物内容清单；保留必要notice；无敏感配置/字体/排除目录；用户批准后再release。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC02](12_SOURCES.md#sc02) [SC12](12_SOURCES.md#sc12) [SC17](12_SOURCES.md#sc17) [CP06](12_SOURCES.md#cp06)

## T38 · 补正调查目录与定向生态贡献
优先级：P2；初始依赖：T01, T05, T23；范围：G8 发布与生态。
源码入口/资产：`corrected atlas；docs/comparison`

**任务意图与起手工作**
SmartCLI纳入通用驱动；列出与各路线的边界；以真实repro向pyte贡献标准一致部分，不提交profile偏好为bug。

**验收门槛**
原58条保留证据层级，新增第59条；不把本轮未重审工具标成已审计。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[SC01](12_SOURCES.md#sc01) [SC05](12_SOURCES.md#sc05) [SC12](12_SOURCES.md#sc12)

## T39 · 等待谓词自身的计算预算
优先级：P0；初始依赖：T01；范围：扩展研究与跨阶段契约。
源码入口/资产：`smartcli_core/readiness.py；输入校验`

**任务意图与起手工作**
检查 regex 编译/搜索和 snapshot 构建能否越过外层 timeout；默认提供 literal；比较受限模式、可超时引擎、隔离 worker，不能用不可取消线程冒充硬超时。

**验收门槛**
有界反例在隔离的纯逻辑测试中结束；取消/截止不被单个谓词永久阻塞；不执行长时间灾难回溯压力。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N16](12_SOURCES.md#n16)

## T40 · 解析完成水位与观测屏障
优先级：P1；初始依赖：T13, T23；范围：扩展研究与跨阶段契约。
源码入口/资产：`引擎适配；事件/observation 协议`

**任务意图与起手工作**
分开 bytes_received、bytes_parsed、frame_committed；异步渲染器要等待解析 barrier，不把 onData 通知当成当前画面已更新。

**验收门槛**
人工延迟 parser 后不会返回声称包含未解析字节的 observation；无 await UI paint 的错误依赖。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N05](12_SOURCES.md#n05) [N06](12_SOURCES.md#n06)

## T41 · 完整 checkpoint 与脱敏重放语义
优先级：P1；初始依赖：T24, T25；范围：扩展研究与跨阶段契约。
源码入口/资产：`事件日志；render checkpoint；导出器`

**任务意图与起手工作**
记录解析器/UTF8残片、两套buffer、光标/pen/modes/scroll margins/Unicode profile；敏感录制允许 discontinuity，不承诺删除原文后还能无损复现。

**验收门槛**
任意记录切点恢复后的同源输入产生相同状态；脱敏或丢帧后显式标记不能精确重放。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N05](12_SOURCES.md#n05) [N15](12_SOURCES.md#n15)

## T42 · shell完成信号的可信度与降级结果
优先级：P1；初始依赖：T16, T19；范围：扩展研究与跨阶段契约。
源码入口/资产：`shell adapters；wait outcome`

**任务意图与起手工作**
对 OSC133/633、exit、侧信道和静默分别标记 evidence_source；不把 nonce 作为对同权限恶意子进程的完整隔离；不擅改用户全局 shell profile。

**验收门槛**
无hook时返回 quiet/unknown 而非 command_completed；伪造标记不会产生高可信业务成功。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N03](12_SOURCES.md#n03) [N11](12_SOURCES.md#n11)

## T43 · 键盘协议协商与能力谎报回归
优先级：P2；初始依赖：T21；范围：扩展研究与跨阶段契约。
源码入口/资产：`input encoder；terminal profile`

**任务意图与起手工作**
研究 kitty progressive enhancement、modifier、bracketed paste；只宣告完整可满足的能力，降级记录具体键损失。

**验收门槛**
终端声明与实际编码一致；模式栈/退出恢复；不支持的键明确失败，不作为字面串打入TUI。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N10](12_SOURCES.md#n10)

## T44 · 语义协议演进：保留未知字段、限制未知动作
优先级：P2；初始依赖：T13, T28；范围：扩展研究与跨阶段契约。
源码入口/资产：`SemanticProvider；schema adapters`

**任务意图与起手工作**
参考 taria 同时保存 relayed tree 与 typed tree；未知观察字段可转发为不可信数据，未知动作不可由模型猜测直接执行。

**验收门槛**
新角色不被静默改名；未广告动作被拒绝；断线不能继续用旧树执行；ACK丢失可诊断。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N14](12_SOURCES.md#n14)

## T45 · 将本地执行工作台融入维护流程
优先级：P1；初始依赖：T01；范围：扩展研究与跨阶段契约。
源码入口/资产：`docs；tools；AI handoff`

**任务意图与起手工作**
使用本计划工具核对当前事实；工作台状态与测试证据分离；允许本地改进工具但不能取消同意/安全边界。

**验收门槛**
换模型后从文件恢复，无需原聊天；失败和skip可追溯；不自动重置脏工作区、不自动commit。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N01](12_SOURCES.md#n01) [N02](12_SOURCES.md#n02)

## T46 · 生命周期与写者租约的状态机测试
优先级：P1；初始依赖：T10, T14, T15；范围：扩展研究与跨阶段契约。
源码入口/资产：`tests；fake backend；virtual clock`

**任务意图与起手工作**
用 Hypothesis state machine 或等价自建模型生成 cancel/close/resize/reconnect/input 交错；一份真值模型与实现互相对照。

**验收门槛**
取消后旧租约不能再写；观察者不消费彼此事件；输入最多一次或明确unknown；失败序列可缩减。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N13](12_SOURCES.md#n13)

## T47 · Windows teardown排空与线程所有权
优先级：P1；初始依赖：T11, T12；范围：扩展研究与跨阶段契约。
源码入口/资产：`WinptyBackend；平台测试`

**任务意图与起手工作**
模型owner单一，但ConPTY阻塞读写/关闭与final-frame drain分离；验证句柄/线程退出而非只看registry空。

**验收门槛**
单PTY串行关闭；输出在关闭过程中仍被排空；未确认结束不标closed；不并发spawn测试。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N07](12_SOURCES.md#n07) [N02](12_SOURCES.md#n02)

## T48 · 慢观察者、丢事件和存储满的显式缺口
优先级：P1；初始依赖：T20, T24；范围：扩展研究与跨阶段契约。
源码入口/资产：`ringbuffer；observer；journal`

**任务意图与起手工作**
区分canonical parser输入不可静默丢与展示层可合并；容量满时暂停/拒绝/受控停止三选一并记录；slow-reader返回gap和resync。

**验收门槛**
磁盘满不假写入；日志缺口不假连续；观测差分和完整快照在可用区间等价。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N05](12_SOURCES.md#n05) [N14](12_SOURCES.md#n14) [N15](12_SOURCES.md#n15)

## T49 · 由能力与测试矩阵生成产品事实
优先级：P2；初始依赖：T34, T36；范围：扩展研究与跨阶段契约。
源码入口/资产：`docs；release manifest；capabilities`

**任务意图与起手工作**
从代码和验证记录生成支持平台、入口、限制；功能存在/测试通过/用户任务成功三层独立，不再人工复制过去的44/44。

**验收门槛**
文档无法把未执行门禁显示绿灯；发布包和源码覆盖分别列出；无过期手写计数。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N01](12_SOURCES.md#n01) [N02](12_SOURCES.md#n02)

## T50 · 可回收的应用recipe与Agent策略
优先级：P2；初始依赖：T17, T26；范围：扩展研究与跨阶段契约。
源码入口/资产：`drive-tui skills；recipes`

**任务意图与起手工作**
将常见Vim/REPL任务做成状态谓词和恢复动作，不保存私密命令；探索限定动作/时间预算；失败生成最小复现而非无限随机按键。

**验收门槛**
recipe带版本/适用范围/终止条件；看不懂时可停止交接；不把屏幕文字当高优先级指令。

**自由实现与反证**
先证明当前代码存在该问题或尚未满足该收益。已有修复可反驳旧任务；相同外部验收下选择更小实现。架构变化写ADR，不把这里的文件名或设计建议当不可更改API。

**收口产物**
最小负例/控制组、实际代码差异、相关门禁结果、未跑范围、review方法、回滚说明。源码变更尤其注意canonical/vendor一致。
来源：[N10](12_SOURCES.md#n10) [N11](12_SOURCES.md#n11) [N14](12_SOURCES.md#n14)
