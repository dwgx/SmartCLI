# POSITIONING — 两次 release 内的选择与不会做的事
依据：[CP1–CP4，E1源码/README，均未运行]。本节是**产品取舍**，不是新的评分或市场胜负证明；旧84/100、65/100仅在历史原包中保留。

## 1. 正面承认重叠
Microsoft tui-test 的当前README明确面向AI agents、终端自动化和测试，覆盖Windows/Linux/macOS、CLI/Rust/Python/JS、locator、四类wait、截图和录制，并标记beta重写。它不是“只给人类测试的工具”，原生Windows也不是SmartCLI相对它的独占优势。[CP1]

| 工程 | 已有焦点（文档/源码证据） | SmartCLI取舍 |
|---|---|---|
| microsoft/tui-test | 统一引擎、多语言调用、丰富输入、定位/断言/录制 | 不补齐其每一种locator/语言/视频格式；优先小范围的可靠状态与Python/CLI/MCP一致性 |
| coder/agent-tty | PTY、追加事件日志、Ghostty快照/图像/视频和reviewable proof | 不自研视频编解码和播放器；借鉴事件顺序、失败证据，复用已有导出生态 |
| onesuper/tui-use | 轻量CLI、持续PTY+xterm/headless、按键/屏幕/高亮 | 不把“能操作TUI”当新卖点；差异化待通过CJK标签、分片、安全进度、明确等待依据等可复现契约证明 |

MCP-first只是集成取舍，不是长期壁垒：别人可加MCP adapter。紧凑JSON是否更省token，Python是否更轻、更快，均未实测，不写成优势数字。真实修复目前的失败，才是下一版可声明的价值。

## 2. 可信交互的具体承诺（待门禁通过）
“我告诉Agent什么被选中，并且文字正确；我知道输入写出了多少；我说明等待满足的依据；不知道时不说完成。”

它不保证Agent决策正确，也不保证所有应用都能发ACK。selected启发式全面校准是后续独立任务，T05修好字符串不等于实现了真正accessibility tree。

继续保留现有Python/CLI/MCP、原生Windows/POSIX和轻量安装。可以逐步让receipt、observer和错误数据更统一，但不为一套理想协议破坏旧调用者。

## 3. 从三家具体借什么，不机械复制
Microsoft `command_settled` 在未有tracker.started时使用300ms quiet，源码等待predicate还对cancel/exit返回settled。这里只说明低层判据，不能据此断言其整个上层取消处理有bug。SmartCLI借鉴等待类别，并显式打印basis/degraded，不把竞品方法名当完成证明。[CP2]

agent-tty 的追加事件/序号和失败传播可参考；其README也写清`run`不是子命令结构化exit status采集，Windows为二级且未CI测试。SmartCLI不把视频作为修复A01/A04的前置。[CP3]

tui-use 的持续write-to-emulator思路可参考；xterm.write入队不是解析完毕，观察必须有处理完成边界。保留SmartCLI已有SS3和双hash，不换成更简单键表。未对其完整wait路径做新实测，不据片段指控运行竞态。[CP4/STD6]

## 4. 明确 won't-do
1. 不重建APNG/GIF/MP4/WebM录制器、视频编辑器或新播放器；需要输出时复用现有工具/格式。
2. 不做竞品性能农场、耗token榜单或批量真实PTY压力测试；只做少量可重复的契约对照。
3. 不做无边界“全能终端平台”：远程运维、云多租户、serial/KVM、GUI远控和所有终端协议不绑进主线。
4. 不更换默认pyte引擎，不为追平别人新增Rust/JS绑定或另一个强制后台服务。
5. 不把任意TUI变DOM、不编造通用app_ack，不把cell启发式标为应用事实。
6. 不承诺跨断线/重启exactly-once、不宣称PTY是sandbox、不承诺无穷输出下同时零丢失/零阻塞/固定内存。
7. 不为了“看起来清爽”删除cmd-art/tui-ui、重命名安装包、重建CodeGraph或改live harness配置。

## 5. 两次 release（能力门，而不是日期或版本号承诺）
**Release A：正确读与不假成功。** T05、T04先过红绿红、vendor和原门禁；T03故障注入达到明确边界再决定收录。POSIX E4尚未验证时如发布库修复，说明适用范围和NOT_RUN，不能宣传“所有平台全部确认”。最小一致性runner及逐条结果在release note可复核。

**Release B：有界服务。** A04 Windows/POSIX分开验证，保留interleave/resize边界、有限队列/关闭、按平台记录行为。A05/A06与之共同影响公平性；若慢回包仍可能占owner60s，不发布“实时可取消/所有请求有低延迟”承诺。receipt从库到CLI/MCP的新增字段做兼容性测试；源码/wheel/skill到达同一能力。

**两版都不承诺**：全终端一致、全部emoji宽度正确、所有app有ACK、通用业务验证、全量无损录制、跨机器共享租约、跨平台bit-exact原始传输、任何模型成功率提升。功能扩展若影响这两版的确定性修复，就移回future backlog，不改现有验收来赶进度。

## 6. 怎样证伪这个定位
若同样四个小契约在三家都已通过且接入成本相同，不能继续拿“可信”当无证据差异。届时优先成为可替换的Python/MCP适配/契约测试组件，或贡献上游，而不是继续补视频和语言种类。这个判断只需少量对照，不需要大榜单。
