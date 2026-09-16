# 我反对本地结论的地方
这不是否定本地Agent：它提供了本轮最重要的真实core证据，`保存→3`和按块SGR缺陷直接接受。以下限定的是推论强度、范围和执行方式。

## 1. “宽字符在前就无条件错误”太强
错误机制确定，独立fixture已经足够；但最终字符串可能因重复内容、空白trim或特定跨度而碰巧相同。从0列开始也并非普遍安全：右边界后若还有字符，字符串切片仍可能多取。附件的某个0列案例恰好一致，不是全称证明。[L1 §1]

还有一个探针oracle细节：`probe_extended.show` 用cell聚合后的 `.rstrip()` 与旧规则的 `.strip()` 比较；含前导空格的行可能多出空白策略差异。这不影响端到端`保存→3`，但v2正式测试两边使用一致标签清理，独立期望用字面量。

补验不需要新大实验：纳入T05同一文件的控制组，含重复标签、0列右界和空白即可。

## 2. “1KiB 100%”不是线上出错概率
已有数据是特定12,395-byte人工流、固定随机分片分布、每档40seed的**最终screen差异率**。31/40=77.5%，1/40=2.5%；原脚本零位小数输出78%和2%属于格式化效果。不能据此说真实用户4KiB read的故障率78%。它还比较最终screen，滚出viewport的早期错误未必被统计。[L1 §2；probe_split_rate.py]

`probe_split_rate.py` 最后打印的是reference.feed_errors，不是每个损坏trial的counter；附件另有“损坏运行feed_errors仍0”的本地结论，保留为上传报告事实，但不说这一个脚本单独证明了它。T04的新fixture会逐case采集counter；不用让本地重跑原40seed。

## 3. interleave 是已修复的快请求通道，不是完整多watcher
必须保护现有能力，这是v1文档缺口；但第二条长wait仍排队。resize本身是一次真实屏幕几何变化，不能被解释为某次按键成功；在legacy路径中保持延后是合理兼容策略，而不是未来永不允许resize的自然法则。[L1 §6；SC3]

此外`list`在INTERLEAVE_OK集合内但不在当前_handle有效分支中，不应据集合成员宣称daemon已经支持该verb。

## 4. 打包有耦合，不代表每次内部改动都改变Registry契约
`smartcli_drive`映射到scripts是真事实；因此改tui.py会触及安装产物和MCP共享路径，必须回归。只要导出路径、参数、响应、协议和registry metadata保持不变，内部调度修正不自动是破坏性公共变更。v2锁定观察行为，不要求每次加循环都升级注册协议。[SC5]

v1并非完全没提vendor：原`MASTER_PLAN.md`第51/123行、`LOCAL_AGENT_PROMPT.md`第33行及`docs/08_MIGRATION.md`第13行都有同步要求。真正缺口是没有把孪生绝对关系/打包映射落实成每个worker的硬触碰边界；不能把“写得不够明确”说成“全文没有”。本轮逐字节保留的v1可直接复核。这不减轻interleave机制在执行架构中确实遗漏的问题。

## 5. “没有POSIX，就只能等T03”不必要
本机不能做POSIX E4，应保留NOT_RUN；但能用真实生产write方法+注入短写/EAGAIN/EINTR做E3逻辑测试。不要让硬件缺口阻止修复。反过来，“真PTY上patch os.write制造短写”属于E4环境中的注入故障，不等同于观察到自然发生短写；报告应双标环境和注入模式。[L1 §3/§9；STD1]

## 6. A04 的内存/阻塞表述是源码推断，不是已完成测量
附件自己把A04列E1且末尾要求补验，这个自我限定正确。Windows现有无界queue没有应用级配额，不保证永不背压或永不受内存限制；POSIX持续写会达到buffer边界，但触发负载/时间仍未测。新的有界queue刻意施加背压，因此不能再用“child完全不阻塞”作为统一验收。[L1 §4/§9]

## 7. “47项通过，1skip”必须按测试摘要记账
附件原文是`Ran 47 tests, OK, 1 skipped`的意思：按unittest通常统计应记总47、通过46、跳过1，而不是47全部通过另加1。旧包自带清单49项可验证完整性，不证明所有测试结果。v2记录total/pass/skip独立数字，不需要为此重跑本地旧套件。[L1 §8]

## 8. Microsoft并非“仅测试框架，不面向Agent”
当前README第一段直接写AI agents；SmartCLI不能靠这个二分定位。无MCP-first已读入口是集成差异，不是永久护城河；对不存在的所有adapter/分支不能下全称结论。[CP1]

## 9. 关于web-chat-archive的hash不一致
按用户报告保留“元数据hash不匹配、脚本hash正确、安装器拒绝、手动安装”的事件。**该原zip不在本次附件中，不能独立确认、重签或声称修好。** `.yaml`也不是理由自动忽略整包校验。新包加入元数据被篡改的负例，先冻结内容再算manifest、再从最终ZIP核验；SHA256只证明一致性，不是作者身份认证。

## 最多三项新的本地实验申请
只新增下面三项，不要求重跑已交E3统计；T05/T04的修复回归属于实施验收，不是额外调研。

**X1／A01注入式字节与状态**：假设原路径在短写2/EAGAIN/EINTR时漏数据或假成功，候选offset循环不漏不重。真实生产方法、fake sink、≤256-byte payload、≤32 write calls、≤1秒虚拟时间；如果candidate任一不同则判负。超过调用预算即停止，不调用真实fd。可先做E3，POSIX E4单列NOT_RUN。

**X2／A04 Windows有界与首帧**：先做容量极小的假模型，证明满queue能被cancel唤醒且字节不丢。若owner再明确批准，一次ConPTY、有限总输出、固定脚本，分别测无人snapshot期间pending和最终解析；candidate仍无界或靠丢字节保持小RSS即判负。总输出上限8MiB、总时间10s、一次一个，超限停止并只收尾自有会话；这些是实验上限，不是生产性能目标。未批准不启动。

**X3／A04 POSIX空闲推进与interleave**：有获批Linux/WSL/容器后，一个PTY子进程先输出受限payload再询问CPR，独立done标志验证不依赖client snapshot。同时用既有fake-session并发测试锁快请求和resize，禁止给两个watcher各配reader。缺done、wrong-order、two-owner或遗留进程即判负；≤1MiB输出、≤10s、仅一个PTY；缺环境标NOT_RUN，不能擅自启动Docker。
