# ORDER — v2 仅修改 R1 顺序和验收
状态：**设计决定**。既有 A03/A02 证据：[L1 §1–2，E3]；A01：[L1 §3，E1，旧替身 E2]。T03/T04/T05 沿用 v1 ID，不重新编号，不改历史状态文件。

## 1. 决定与理由
**实施及合入：T05 → T04 → T03。** 这不是跨平台全局严重性排序，而是在目前 Windows 本机、A03 用户可见且最小可证的条件下的交付顺序。T05 已有真实 `保存 → 3`；T04 已有分片导致残渣和控制组；T03 的生产短写路径未做真实 POSIX 验证，且涉及部分输入的恢复。

取消 v1“R1 三项任意并列”的执行建议；不再要求 T01 重建已存在的 CodeGraph，不把 T02 当作必须先新增一个集中大测试文件的前置。T02 的意图分别由每个变更自己的失败测试满足。

可并行：只读研究和在独立 RUN 中的纯内存模型。不可并行：两个 writer 修改同一工作树／同一个 canonical 或 vendor。T03 的模拟输入状态设计可提前，但不得先合入抢占 T05/T04。

## 2. 共同保留项
`INTERLEAVE_OK` + `_drain_interleavable()` 的快操作可响应性、session 单 owner、resize 不插进 legacy wait、token 检查、`on_poll`、双 hash、SS3、主/备屏、CPR 回复，都不是重构时可删的旧代码。[L1 §6–7；SC1–SC4，E1]

canonical 改完，必须同步 vendor；scripts 路径也是安装包 `smartcli_drive`，不得通过改目录“顺手整理”。不过纯内部改动并不自动构成公共 API 或 Registry 元数据变更；真正要锁定的是可观察契约。

## 3. T05：cell span 标签，首先交付
最大触碰面：**3 个文件**：`smartcli_core/snapshot.py`、其 vendor 孪生、`tests/test_cell_span_regression.py`（新增）。不改 ScreenModel，不改启发式选中策略，不新增依赖或公开 API。

最小测试必须走真实 `ScreenModel.feed → build_snapshot → selected/menu_items → to_json/to_text`，独立期望是字面量 `保存`，不是用被测 helper 计算期望。
```
  1) 打开   2) ESC[7m保存ESC[0m   3) 退出
```
原始输入详见 `tests_product/test_cell_span_regression.py`。同时保留 ASCII、中文前缀+ASCII 高亮、emoji 前缀、组合符前缀、0 列跨度、正文不变等控制组。原 `.strip()` 的标签清理行为保留；不能把标签文字当作 raw span 内容协议来扩需求。

最小修法：从 `[a,b)` 的 cells 聚合 data，续格空串不新增空格。可以直接写一行，也可以引入 private helper；不要求新建公共 `cell_span_text`。本轮跨度规则是**基字落在范围内才纳入**；起点若仅命中续格，不倒取范围外的基字。ZWJ 字形宽度的全面修复不塞进本增量。

验收（PowerShell，使用现有解释器）：
```powershell
& $Python -B tests/test_cell_span_regression.py
& $Python -B tools/sync_vendor.py --check
& $Python -B tests/test_vendor_sync.py
& $Python -B tests/test_terminal_fidelity.py
& $Python -B $Kit/tools/conformance.py --repo $Repo --case screen --consent-execute-reviewed-code
```
禁止：把 `3` 加为允许答案、对中文 skip、只断言非空、硬编码菜单字符串、改变 oracle 来迁就 bug、自动重跑抹掉首次失败。

## 4. T04：分片不变 + 独立语义，不止“和一次 feed 一样”
最大触碰面：**3 个文件**：`smartcli_core/screen_model.py`、其 vendor 孪生、`tests/test_sgr_stream_regression.py`（新增）。若必须扩到通用 parser／新依赖，先停下给出最小反例及范围提案。

必须分成两类 oracle：
A. 同字节流整体／每个切点／逐字节／固定种子随机切分，比较所有 cells 的 data、公开属性、cursor、title、alt_screen、app_cursor；不是只比较第一行。
B. 确切支持子集的独立属性断言。例如 `38:2::255:0:128` 必须是 RGB `ff0080`，`4:3` 降级成普通 underline 时不得附带 italic；不能让“整体和分片一起错”通过。[STD3，E1]

必须保持普通 SGR/CSI/OSC、UTF-8 分片控制组。不把 OSC/DCS 字符串负载中的类似 `ESC[4:3m` 子串全局重写。7-bit escape 路线与 UTF-8 解码分开；不能把 UTF-8 continuation byte 当 C1 控制。

实现候选：有限状态的增量 SGR 规范化层，或在现有 parser dispatch 上局部修正。仅**完整且确定是 CSI SGR**时改写；明确空 color-space 槽、unsupported 58 underline-color 的忽略规则，不能盲把全部冒号改成分号。未知格式只丢该属性组，不把其数字误用成 bold/italic 等其他属性。

未终止 CSI 暂存上限建议 1024 字节（设计起点，非已测最优值）。超过上限进入有界 discard-until-final/abort；后续合法 `OK` 必须恢复，不把残渣绘入屏幕。不要缓存整个 OSC/DCS 负载；其处理继续交给已有流解析器。单个单元测试不需要百万字节，更不需要真实 PTY。

```powershell
& $Python -B tests/test_sgr_stream_regression.py
& $Python -B tests/test_cell_span_regression.py
& $Python -B tools/sync_vendor.py --check
& $Python -B tests/test_vendor_sync.py
& $Python -B tests/test_terminal_fidelity.py
& $Python -B $Kit/tools/conformance.py --repo $Repo --case sgr --consent-execute-reviewed-code
```
本包的 `tests_product/test_sgr_stream_regression.py` 覆盖分片和语义核心；超限恢复/嵌套字符串等实现相关测试由 worker 补在同一新测试文件，不能因模板没有该项就省掉验收。

## 5. T03：可以先模拟，但不能把模拟当真 POSIX
见 `A01_MINIMAL.md`。最小库修复最大 3 文件（backend、vendor、一个测试），需跨 session 的 receipt 可放到后续独立增量，最高 5 文件，另报范围。不修改抽象 `write(data)->None` 既有成功语义：全部写完才正常返回；未完必须抛携带偏移的错误，不返回伪成功。

最小 fault schedule：短写 2 字节 → EAGAIN → EINTR → 短写 1 字节 → 余下。断言接收器恰好得到输入一次、offset 单调、无 busy spin、取消/timeout 保留 partial。故障注入实际生产方法可在 Windows 做；标 **E3 + injected os.write**，不是 E4。真 POSIX raw-mode 单 PTY 用 child hash/length 做独立裁判，未运行则保留 NOT_RUN。

```powershell
& $Python -B tests/test_partial_write_regression.py
& $Python -B $Kit/tools/conformance.py --repo $Repo --case input --consent-execute-reviewed-code
& $Python -B tools/sync_vendor.py --check
```
任何 real PTY、Docker/WSL 启动都不是这些命令的隐含动作。

## 6. 红 → 绿 → 回退修复再红 → 恢复绿
已有 E3 原版证据不用重新量化；但**新测试**必须证明它能抓到 bug。操作在独立经批准的验证副本，不在脏工作树执行 reset/revert/stash。旧版与候选的测试文件必须字节相同。

1. 原版组件 + 新测试：指定业务断言失败；import 失败、依赖缺失不算红。
2. 候选组件 + 同一测试：通过。
3. 候选测试保持不变，只还原针对性修复逻辑：同一业务断言再次失败。
4. 恢复候选，相关控制组通过，记录 diff 和文件 hash。

T05 回退 cell 聚合为 display 字符串切片；T04 回退成按块 `_SGR_COLON.sub`；T03 回退成单次 `os.write` 丢返回值。不能删测试、改 expected、回退整个新测试一起制造“红”。若现在 refactor 使该 mutation 无法命中，记录 `MUTATION_NOT_APPLICABLE`，设计针对新实现的等价 mutation，不能填“通过”。

`templates/CLOSURE_V2.json` 规定四阶段结果。不同平台开列：`unit_memory=PASS` 不会自动关闭 `posix_pty=NOT_RUN`。
