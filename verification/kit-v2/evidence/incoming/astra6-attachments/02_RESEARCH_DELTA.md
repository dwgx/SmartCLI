# 新研究与上一轮结论纠偏

## D01：更丰富的wait名字不等于更强证据

Microsoft固定源码的command_settled在没有tracker.started时回退到300ms静默；取消和退出也会使部分内部wait结束。[N03] 不能据此直接宣称整个产品错误：还需审查外层取消与结果映射。能够确定的是，SmartCLI的设计必须区分wait停止、条件满足、命令结束及业务成功。

采纳：多类wait、命令tracker和输入开始基线。不要照搬：把fallback结果藏在统一成功返回后。本地试验：缺shell hook、屏幕静止但进程未退出、输入未提交、取消与完成同拍；逐一检查completion_basis。

## D02：持续PTY读取还需要parser提交屏障

xterm.write先排队，callback才表示特定块被解析；onWriteParsed也可能在还有pending writes时触发。[N05,N06] 前轮读取tui-use的onData路径出现write之后立即notify，应把它当“待跟踪完整wait代码的竞态候选”，不是已运行确认的bug。[N17]

采纳：事件驱动与高低水位。SmartCLI新接口需要分别暴露received/parsed/committed，而不是以最近收到字节时间证明snapshot新鲜。静态pyte同步feed也要定义同样语义，为将来引擎插拔留一致契约。

## D03：Windows关闭要求I/O继续推进

Microsoft说明ConPTY关闭可能输出final frame，通道与响应若未继续处理可能造成deadlock。[N07] 单owner只约束屏幕状态，不应把阻塞平台读写、关闭、JSON回包全部塞进同一个线程。

采纳：平台I/O与模型mutation分离。不要把“开始close”记成“已退出”；优先返回closing，再通过真正的退出/handle结束验证。真实测试一次一个PTY。

## D04：语义原文与动作验证可以用不同表示

taria的bridge保留原tree字段供观察，同时用typed解析结果判断动作；watch跟踪状态，broadcast发布ACK，并有输入队列/行长上限。[N14] 这是比“加一个DOM字段”更有价值的设计。

SmartCLI可允许未知观察角色透传，但未知动作不执行；断线必须使action失效。原tree仍是应用提供的不可信数据，不能凭“native”成为系统指令。ACK只说明应用处理，不能替代最终文件或业务断言。

## D05：MCP长任务是可选适配，不是内核前提

先实现独立cancel waiter、interrupt application、close session，再根据客户端能力映射。固定2025-11-25规范区分request cancellation与task cancellation，Tasks仍标experimental。[N08,N09] 本地部署时重查实际SDK和客户端能力；无需为了它立即大版本迁移。

## D06：按键不是字符串别名表

kitty协议设计包含渐进能力与事件类型；模式需要应用协商。[N10] 不能给未知键发字面“Ctrl+Shift+...”到Vim当兜底，也不能宣告一个不能实际处理的增强位。保留现有DECCKM/SS3，在能力profile内扩展。

## D07：shell标记有可信度边界

VS Code公开OSC633/133、command和exit标记，E序列带可选nonce以抑制部分命令伪造，并区分集成quality。[N11] SmartCLI可以用这些机制改善命令生命周期，但不是给所有不可信同权限子进程提供密码学隔离。标记来源、hook质量和降级原因必须可见。

## D08：同步谓词本身可能越过外层deadline

当前readiness在owner路径同步执行regex搜索。[N16] 这是新补入T39的代码推论：外层clock检查不等于单次search可抢占。本轮不执行大规模恶意regex负载；本地先用受限小fixture或替身验证时钟/取消契约，再比较literal/受限regex/独立执行单元。

## 检索边界

本轮不是全网重新穷举，而是围绕前轮候选继续查一手源码和官方协议。GitHub连接器读取成功；容器直接clone因DNS失败，下载也未取得完整源树；本环境缺pyte。所以未增加任何SmartCLI真实运行通过率、竞品速度排名或平台成功声明。工作台自身测试是另一类证据。
