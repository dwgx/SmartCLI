# 建议架构与可替代决策

本文定义要解决的语义，不强制目录命名和框架。新增API/字段是设计草案，不是当前SmartCLI已经支持的命令。

## A. 分离三种接口

Transport：PTY/ConPTY字节与进程；TerminalEngine：解析、cells、modes、queries、snapshot；InteractionRuntime：请求、watcher、writer lease、证据、适配器。Python库可以内嵌运行时，CLI/MCP复用相同服务，不把IPC私有函数当永久公共SDK。

现有PtySession可先作为兼容 facade；ScreenModel默认仍是pyte实现。可选引擎需通过共同契约测试后才加入，未被测的能力报告unsupported。

## B. 单owner，多个非阻塞观察者

owner按有限budget处理入站字节、模式更新、输出应答、write进度、watcher判断与状态发布。I/O线程只收发有界消息，不直接改pyte。网络writer、磁盘writer、图片渲染消费不可变快照，不共享会清dirty的对象。[N04,N05,N07]

两种可选实现：线程+selector+消息队列，利于保留同步PythonAPI；async actor，利于多watcher/cancel但须处理同步ConPTY桥。选较小、可验证的方案，而不是为了异步而异步。

## C. 标识与因果边界

session_id可复用名字，但session_generation每次创建必须变化。observation revision在owner提交状态时递增，不依赖CRC唯一性。geometry_epoch在resize变更。writer_lease_epoch用于撤销旧输入权。大整数经过JSON时可用十进制字符串避免消费者精度损失；必须写进schema。

action_id用于追踪请求，不保证跨崩溃exactly-once。内存dedup只能覆盖存活期；请求部分写入后断线应返回unknown/partial，不能盲重发全部输入。lease在接受和真正写入前检查；已进入操作系统/应用的字节无法撤回。

原子act-observe只保证自己的入队/基线采样顺序。后台动画可以同时变化；需要指定谓词、区域或应用ACK才能增强证据。native ACK仍不是业务裁判。

## D. 五种不同的等待语义

`state_matches`允许旧状态已满足时立即成功；`state_changed`要求相对基线变化；`screen_quiet`只是画面/区域安静；`command_finished`必须有命令边界证据；`process_exited`必须有退出状态。不要把已有regex全部改成edge-triggered，破坏合法“等待当前条件”的调用。

Outcome至少含status、basis、observed_revision、elapsed、timed_out/cancelled、snapshot、degraded_reason。非支持命令hook时返回quiet/unknown；别把fallback偷偷包装成command_finished。[N03,N11]

取消wait只解除该watcher；interrupt要求应用级输入/信号权限；close销毁session是另一个权限。协议取消与客户端断线需要配置行为而不是默认杀目标。[N08,N09]

## E. 字节与状态的分片契约

同一字节序列任意分片必须等价，包括UTF8、CSI/OSC/DCS、SGR子参数、ST双字节边界。每层都保持incremental state；禁止对单read块做假设完整序列的正则预处理。对未知/坏序列记录parser degradation，不继续输出无警告“准确状态”。

Parser barrier：received_bytes ≠ parsed_bytes ≠ committed_revision。同步pyte可以一次feed同步推进；异步xterm需等相应callback/watermark。onWriteParsed不是所有待处理写入已全部完成的证明。[N05,N06]

## F. 感知与diff

cell范围统一半开区间、0-based；JSON明确rows/cols顺序。字符文本通过cells聚合，不对展示字符串用列下标切片。聚类、续格和Unicode width policy单列。selected候选保留style证据、heuristic_reason、confidence或unknown。status/errors是提示，不是已验证事实。[N12]

每个observer持有自己的revision游标；环形buffer覆盖后返回gap+可重置完整快照。展示可合并无关帧，canonical bytes不能无声丢失。region稳定可过滤动画，但过滤mask必须在证据中可见。

## G. 事件记录与checkpoint

日志事件至少含generation、sequence、monotonic时序、事件类型、输入/输出方向、大小、完整性与脱敏状态。原始bytes可使用base64保真，而不是先错误解码再丢弃；不要默认持久化所有敏感输入。

checkpoint不仅是屏幕cells，还包括decoder/parser残片、cursor/pen、modes、两屏buffer、scroll region、tab stops、字符集、终端profile、Unicode版本。不能恢复的状态要从更早raw事件重放，或明确不支持该切点。

录制重放默认只消费输出/resize重建画面，绝不自动再次执行当时输入。脱敏日志和精确重放可能冲突：可以生成公共redacted展示与私有完整证据，或标注不连续；不能声称脱敏后仍无条件bit-exact。[N15]

## H. 语义适配

SemanticProvider返回应用声明的tree/ACK及版本、覆盖范围。原文字段可以保留供阅读，typed结构用于动作校验；未知action一律拒绝，unknown role只影响局部显示。session断线使旧tree不能用于新动作。[N14]

先用tui-ui自家控件试点，再考虑Neovim/Textual/taria。不要做“推断树”和“原生树”相同的信任等级。公共协议优先小而透明，不追求第一次就统一全部终端生态。
