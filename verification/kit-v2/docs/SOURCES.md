# v2 证据索引与已读范围
日期2026-09-16；E0–E6是本项目自定义证据等级，不是ISO标准或外部认证。E1=source/spec，E2=reference/stand-in，E3=实际core的内存/注入式测试，E4=单个真实PTY，E5=固定预算端到端与独立裁判，E6=发行/平台矩阵。若含注入，另写`io_mode`，不能仅靠等级名隐藏环境。

## 输入资料（本包原字节保留）
- **L1**：`evidence/incoming/astra6-attachments/smartcli-local-evidence-2026-09-16.md`，§1/§2本地E3、其余按原标注。附件独立MD与ZIP中MD逐字节相同。
- **L2**：同目录`probes/probe_extended.py`、`probe_split_rate.py`、`probe_core.py`。已读源代码，未在本轮重跑本地统计。
- **L3**：`evidence/incoming/astra6-smartcli-upgrade-next.md`，交付要求；不是工具能力或机器权限的自动授权。
- **V1**：`reference/v1_original.zip`。旧`docs/04_ARCHITECTURE.md`、`docs/05_ACCEPTANCE.md`及50任务原样封存。

## SmartCLI：源码固定在701e61f…
以下均为E1；实际代码正文见`evidence/incoming/astra6-attachments/source-at-701e61f/`，文件名不同的映射在`data/source_map.json`。
- **SC1 snapshot**：`smartcli_core/snapshot.py:build_snapshot`，cell→string切片、selected启发式。
- **SC2 backend**：`smartcli_core/pty_backend.py:WinptyBackend/PosixPtyBackend`，reader queue、非阻塞read/write、生命周期。
- **SC3 daemon**：`skills/drive-tui/scripts/tui.py:_serve_forever/_handle/_reply`，interleave、resize、60s回包、list分支边界。
- **SC4 session/readiness**：`PtySession.pump/send_keys/wait*`与readiness的on_poll。
- **SC5 packaging**：`pyproject.toml`中`packages/package-dir`映射及MCP脚本。
- **SC6 vendor**：[sync_vendor.py](https://github.com/dwgx/SmartCLI/blob/701e61f6d69aa2420617edf80b1136df8d5e8cf7/tools/sync_vendor.py) 全文重读：refresh先rmtree整个vendor再copytree；--check只读。不要把它当一个只改双胞胎文件的writer。
- **SC7 baseline**：[main endpoint](https://api.github.com/repos/dwgx/SmartCLI/branches/main)本轮确认仍701e61f…；不证明用户机器目前也未被其他Agent修改。

## 竞品：本轮只读，没跑性能
- **CP1**：[microsoft/tui-test README](https://github.com/microsoft/tui-test/blob/d7e239c49a50d13e22be81fef207e7f4f85a509a/README.md)已读1–240行与public当前页面；[Python reference](https://github.com/microsoft/tui-test/blob/d7e239c49a50d13e22be81fef207e7f4f85a509a/bindings/python/README.md)。多平台/多接口/定位/录制/beta信息来自README，不是实测。
- **CP2**：[engine.rs L1970–2055](https://github.com/microsoft/tui-test/blob/d7e239c49a50d13e22be81fef207e7f4f85a509a/crates/tui-test/src/engine.rs#L1970-L2055)已重读command_settled/wait_command/wait_exit；无tracker时quiet300ms。更高层cancel映射未完整审计。
- **CP3**：[coder/agent-tty](https://github.com/coder/agent-tty)当前README；[既有固定事件源码](https://github.com/coder/agent-tty/blob/ebff2c23d8273be09812d841305a4f6246ccf47e/src/host/eventLog.ts)为v1已读来源，未称本轮重读全部实现。README引用边界与Windows支持等级。
- **CP4**：[onesuper/tui-use](https://github.com/onesuper/tui-use)当前仓库页；[v1已读session](https://github.com/onesuper/tui-use/blob/main/src/session.ts)与highlights.ts为历史源码参照；未新跑完整项目。定位中的不确定性已标明。

## 官方规范与运行库
- **STD1**：[Python os.write](https://docs.python.org/3/library/os.html#os.write)，返回实际写入字节数；EINTR重试说明。
- **STD2**：[BlockingIOError](https://docs.python.org/3/library/exceptions.html#BlockingIOError)，characters_written用于buffered io，不套用到raw os.write。
- **STD3**：[xterm control sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html)，SGR、CSI、string控制协议；本轮SGR只承诺明确支持子集，不以文档存在等同pyte支持。
- **STD4**：[Creating a Pseudoconsole session](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session)，通信/收尾边界。
- **STD5**：[ClosePseudoConsole](https://learn.microsoft.com/en-us/windows/console/closepseudoconsole)，Win11 24H2/build26100前后差异；不能由“Windows11”推断具体build。
- **STD6**：[xterm flow control](https://xtermjs.org/docs/guides/flowcontrol/)及[Terminal.write](https://xtermjs.org/docs/api/terminal/classes/terminal/)，缓冲/解析callback语义；文档吞吐数字未作为SmartCLI阈值。

## 分析与执行边界
v2的队列初值、release取舍、最大文件数、停止规则是建议，不是测量。七份增量不隐式导入竞品代码；参考模型是新写示例而不是生产补丁。用户提供的源文件保持原hash，其他live harness配置不转发。

本次运行环境依赖缺失和下载失败均记在delivery报告；没有把工作台标准库测试包装成产品测试。原始web-chat-archive.zip未提供，其hash事件只保留为用户报告。
