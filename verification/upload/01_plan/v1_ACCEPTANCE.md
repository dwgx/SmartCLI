# 验收门槛：先证明正确，再比较效能

## 证据等级

E0：待验证假设。E1：固定commit的源码/规范。E2：提取逻辑或替身。E3：实际导入本地core的纯内存测试。E4：本机一个真实PTY的串行验证。E5：固定二进制/模型/预算的端到端任务与独立裁判。E6：源码、wheel、独立skill及平台矩阵的发行验证。

等级不是分数：E3可证明某个解析不变量，比一段没有裁判的E5演示更有针对性。每条发现写scope，不让“实际代码测试”被误读为跨平台真实终端测试。本包工具测试属于workbench，不属于上述产品验证的绿灯。

## 必须有的负例与控制组

| 家族 | 负例 | 控制组/验收 |
|---|---|---|
| 输入完整性 | 每次只写1..N字节，间歇EAGAIN/EINTR，半途取消 | 字节无重发/丢失，报告written_bytes与partial，不将队列接收当写完 |
| 分片 | 每个边界和随机chunk切CSI/UTF8/SGR | 与同序列整体feed的cells/attrs/cursor一致；另有规范/参考终端语义比较 |
| cell坐标 | CJK+emoji+组合符+突出显示 | ASCII对照一致，边界切续格规则明确 |
| 生命周期 | start中途失败、exit先于wait、close与final frame交错 | 清理自己拥有的资源，未确认退出保持unknown/closing |
| wait | 旧prompt、quiet但未完、spinner、slow regex、cancel与满足同时 | 各自Outcome明确，不额外声称命令或业务完成 |
| 多观察者 | A读diff后B读、慢B错过ringbuffer | 互不消费，gap可诊断，可resync |
| writer | 旧lease排队后被人工接管、重复请求、部分写后断线 | 旧lease不再写；已写字节不可回滚需告知；不虚构exactly-once |
| 证据 | 磁盘满、日志中断、秘密回显、checkpoint半个escape | 缺口/脱敏可见，回放不重执行命令，不公开秘密 |

## 运行级别

Static：导览/AST/源码检查。Memory：经审查的单个纯内存脚本，使用已有虚拟环境。Loopback：fake session的真实socket/thread测试，仍须资源预算与清理。PTY：一次一个真实会话、串行执行。Heavy：run_all、verify_fx、大型差分/竞品批次，单独获批后运行。

agentctl默认只允许显式审查后运行列入白名单的Memory项；loopback、PTY、Heavy由它拒绝。没有“相信Agent所以忽略所有同意”的参数。超时/日志上限不是内核sandbox，测试入口未来变化需重新审查。

## 阈值政策

输入/解析不变量应精确比较；时间与内存阈值先在本机测基线、留调度噪声裕量，再在隔离平台校准。不能为了通过一个回归任意放大阈值。性能基准重复次数和预算须提前定义；资源密集真实PTY不在用户主机上密集重复。

## 任务关闭

verified记录必须附验收列表、证据文件、代码指纹、运行范围、未跑项、评审方法和回滚说明。refuted要有反证或新版已修复证据。仅“看了代码觉得没问题”可以关闭源码侦察任务，不能关闭需要E4/E5的产品承诺。

state工具只验证结构/文件存在/hash，不能为Agent内容真实性背书。自评就是self-review，不冒充第二个独立模型。第一轮失败保留，不把PASS_WITH_SKIP按PASS计入验证范围。
