# BRIEFS_V3 — 三份可派发的工作单、三项补验与唯一续接入口

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 0. 主 Agent 先执行的规则

【我的推断／设计】只派一个repo writer。本文是v3增量，T05/T04/T03保持已完成；不要重新实施，也不要重跑它们的原始调研。读取当前HEAD加已有工作树overlay，沿用已存在CodeGraph；调用图不解析抽象backend路径时回到源码，不因图上缺边就判定代码未使用。保留所有owner既有修改、模型配置、技能目录和缓存位置。[^L00]

【我的推断／设计】仓库变更只在获准的 `D:\Project\SmartCLI`，新RUN放在owner批准的 `D:\Project` 下且在源码和冻结计划包之外。没有commit/push/tag/release、全局安装、改系统配置、付费模型、启动Docker/WSL或大规模PTY的默示授权。下述worker可自行选择内部实现，但不能换验收、扩大触碰面或自动激活后续切片。

【我的推断／设计】所有source touch按**物理文件**计数，包括canonical、vendor、测试登记、MCP wrapper与新文件。不能把“一个目录”“一对孪生”计为一个文件；不能临时把新测试塞到旧无关文件规避上限。RUN里的收据不是产品文件，但必须只写批准RUN，不能借此修改别处配置。

【证据支持·E1】`smartcli_drive`发行包映射到 `skills/drive-tui/scripts`；daemon与MCP不是只用于仓库的开发脚本。[^LCPKG]
【我的推断／设计】任何daemon改动同时需要记录CLI/MCP/wheel影响；尚未做发行验证就写E6 NOT_RUN，而不是动pyproject映射规避测试。

## 1. Worker W1 — A04生产：先一片，再下一片

### 可直接粘贴的目标

【我的推断／设计】你负责A04的最小生产增量，不负责把整个runtime重写为actor。先读 `A04_PRODUCTION.md`、附件 `03_receipts/A04P_PROPOSAL.md` 与当前三个已修复模块。默认只申请并执行**S1预算传输基础**；S2/S3/S4/S5/S6是后续独立授权单元，不得一次扩大diff。

【我的推断／设计】第一份产物是RUN中的小提案：说明采用私有预算能力还是新增optional kwarg、默认旧调用怎样保持、未知pending怎样表示、byte cap覆盖哪些内存、close阻塞怎样处理。新增线程、队列、public API字段/参数或默认引擎必须写入待批准栏。提案未获批准时停在文档，不启动产品修改。

### S1目标文件与上限：6个

| 文件 | 允许触碰的符号／内容 |
|---|---|
| `smartcli_core/pty_backend.py` | 两个backend的读路径；拟新增私有budget/status能力；不改T03 write语义 |
| `smartcli_core/session.py` | `PtySession.pump`的内部预算配置/可见cut；默认旧行为保留 |
| `skills/drive-tui/_vendor/smartcli_core/pty_backend.py` | 仅同步对应canonical |
| `skills/drive-tui/_vendor/smartcli_core/session.py` | 仅同步对应canonical |
| `tests/test_a04_read_budget.py` | 新回归：真实生产方法+注入transport |
| `tests/run_all.py` | 只登记该测试，不改旧测试顺序、阈值或重跑规则 |

【我的推断／设计】不得修改screen_model/snapshot、MCP/daemon、pyproject、技能说明、依赖或引擎。必要时提出S2/S2p，不偷进S1。官方vendor同步默认refresh会影响整目录时，只同步本片允许的文件，随后执行官方只读核对；对vendor已有独立修改先停，不覆盖。目录整体删除/重复制不是三行代码级安全同步。

### S1验收与允许的实现自由

【我的推断／设计】验收必须通过：单次/单轮budget不被持续可读源突破；多轮拼接已交付流没有丢失或重复；预算恰好耗尽不能自动报告drained；旧zero-arg backend仍可被默认pump调用；backend内部TypeError不会触发二次读取；被动能力未在daemon默认启用。具体数据结构由worker决定，但新增队列需审批。

【我的推断／设计】以当前仓库为cwd，下面的**新文件测试命令仅在该文件按提案创建后运行**。现存已完成三项的测试，只在相关改动影响其路径时作为防回退，不重跑历史原生测量：

```text
python -B tests/test_a04_read_budget.py
python -B tools/sync_vendor.py --check
python -B tests/test_vendor_sync.py
python -B tests/test_partial_write_regression.py
```

【我的推断／设计】在RUN的隔离验证副本里，删除本片预算机制或让切面错误报告drained，原测试必须失败；恢复候选后通过，测试文件hash不变。不得对原工作树执行reset/stash/revert，也不得改T03旧单写实验来凑新的E4结果。

### 后续分片，不得跨过门槛

【我的推断／设计】S1收据完成后，下一个候选是S2 readiness cut（6文件），再单独S3 daemon service/io透传（5文件）。S3必须保留 `INTERLEAVE_OK` 集合与resize排除，且在空闲、请求之间、长wait中使用同一配额。它不是“加一个空闲pump”就结束。新增测试名与目标文件按 `A04_PRODUCTION.md` 表，不临时扩大。

【我的推断／设计】S3完成后允许的验证入口（需要相应授权，loopback不等于纯内存）：

```text
python -B tests/test_a04_daemon_service.py
python -B tests/test_a04_io_surface.py
python -B tests/test_daemon_concurrency.py
python -B tests/test_readiness.py
python -B tests/test_wait_any.py
python -B tests/test_wait_change.py
python -B tests/test_visual_change.py
```

【我的推断／设计】Window有界buffer S5不能先于关闭契约S4直接启用。新teardown helper需要另批；full buffer关闭状态不能入数据队列。同步输入/write与device reply必须保序；不要从write中重入整个pump。第二个长wait仍排队，不能声称已实现多watcher。

### 停止与收据

【我的推断／设计】出现任何条件立即停：超过允许文件；要改公共API却未批准；vendor已有不同修改；旧修复回退；调用图与实际文件归属不清；需要新线程/队列/依赖；native调用可能阻塞却没有监督边界；测试阈值必须放宽才能过。只交最小问题与提案，不自动“修遍全仓库”。

【我的推断／设计】收据至少含：slice_id、before/after overlay hash、全部changed_files、原始first attempt、负例/变异四阶段、preserved behaviors、`runtime_fixed_scope`、未修A05/A06、下一片。S1即使全绿，也写 `a04_daemon_fixed=false`。NOT_RUN示例：

```json
{
  "slice": "A04-S1",
  "evidence": "E3",
  "a04_daemon_fixed": false,
  "accepted_prior_evidence": ["T05/E3", "T04/E3", "T03/E3+E4", "X2/E4", "X3/E4"],
  "not_run": [
    {"scope": "new_daemon_native_posix", "reason": "S3 not implemented/authorized"},
    {"scope": "new_winpty_cap_native", "reason": "S4/S5 not implemented/authorized"},
    {"scope": "release_wheel_and_standalone_skill", "reason": "E6 not executed"}
  ]
}
```

## 2. Worker W2 — conformance加固：让错误答案真的被拒绝

### 可直接粘贴的目标

【我的推断／设计】你只改获准的验证工作副本，不改SmartCLI产品源码。读取 `EVIDENCE_STANDARD.md` 与附件现存 `05_verification/conformance.py`。保持现有case与CLI兼容，不把 `--case all` 偷换成六轴认证。先实现只读review+错误证据拒绝，再按产品已具备能力接入native/cancel profile；能力缺失要明确报告。

【我的推断／设计】`<VERIFY_ROOT>` 指owner批准的**可编辑工作副本**，不是不可改的下载ZIP或本次冻结v3目录。先打印现存conformance脚本路径/sha，再执行。不得改旧包清单让历史包看起来从未变化；新版本另生成清单、另给hash。

### 目标文件与上限：7个验证包文件、0个产品文件

| 目标 | 作用 |
|---|---|
| `<VERIFY_ROOT>/conformance.py` | 保留旧CLI，显式profile与basis origin，首轮结果/导入路径 |
| `<VERIFY_ROOT>/verify_evidence.py`（新） | offline review/reject-controls/explain，不执行包内代码 |
| `<VERIFY_ROOT>/credible_schema.json`（新） | 六轴、来源、scope、NOT_RUN与互斥状态 |
| `<VERIFY_ROOT>/credible_fixtures.py`（新） | 小型正确/错误证据fixture，仅验证器用 |
| `<VERIFY_ROOT>/test_credible_evidence.py`（新） | 真正调用verifier的负例，不只比较两个常量 |
| `<VERIFY_ROOT>/test_conformance_contract.py`（新） | 旧参数、输出上限、退出码、导入来源与profile兼容 |
| `<VERIFY_ROOT>/MANIFEST.json` | 只为新工作副本生成，不动旧产物 |

【我的推断／设计】若当地验证包原有目录结构不同，先给一一映射，经主Agent确认后沿用原结构；不得因路径不同直接复制覆盖。必须更动第8个文件时停并拆片。输出evidence放NEW_RUN，不包含在冻结输入manifest中。

### 必須保留与新增拒绝

【我的推断／设计】保留原 `--repo`、`--case`、`--consent-execute-reviewed-code`、`--out` 限制；没有许可不import目标core；输出路径不能在repo或冻结工具目录；不得自动安装依赖。旧实验收据只做静态引用，不以本次新验证器运行代替旧E3/E4记录。

【我的推断／设计】第一片新增实际拒绝：metadata hash错、额外/缺失文件、路径逃逸、run不匹配、selected假值、输入长度/hash矛盾、partial却写written、budget_limited却强称complete、adapter来源冒充runtime、取消响应冒充进程退出、close_unconfirmed冒充closed、事件缺口仍声称完整replay。每条通过实际verifier取得非零拒绝，不能以“我在测试里知道它不对”代替。

【我的推断／设计】收据schema允许raw原件与derived report并存；保留35/44的provenance_conflict，不自动选值。离线review不import第三方代码；JSON尺寸/深度/条数超界明确拒绝；不能利用hash核对读取任意绝对路径。sha只证明内容完整，不宣称来源认证。

### 验收命令与停止

【我的推断／设计】在新脚本存在并通过审查后执行；第一条标准库unittest，后面是本brief新增接口：

```text
python -B -m unittest discover -s <VERIFY_ROOT> -p "test_*.py" -v
python -B <VERIFY_ROOT>/verify_evidence.py review --bundle <VALID_EVIDENCE>
python -B <VERIFY_ROOT>/verify_evidence.py reject-controls --bundle <VALID_EVIDENCE> --out <NEW_RUN/negative-first.json>
python -B <VERIFY_ROOT>/verify_evidence.py explain --bundle <VALID_EVIDENCE>
```

【我的推断／设计】不要为了使native/cancel六轴通过而在harness偷偷实现runtime不存在的能力。没有对应产品接口则该profile返回UNSUPPORTED，子case能通过就单列。只有offline review的版本可立即作为审阅工具交付，不能挂“现场可信交互全部通过”标签。

【我的推断／设计】停止条件：验证器能被一个已列负例骗过；需要执行未受信证据包代码；要改产品源补feature；需要新网络服务/模型；必须修改历史raw文件；增加自动重跑；缺项被计为PASS。输出 `verification_tool_tests` 与 `product_tests` 两张表，不能合并统计。

【我的推断／设计】NOT_RUN必须写清：`new_credible_native_profile: NOT_RUN/UNSUPPORTED`、`macos: NOT_RUN`、`product_release: NOT_RUN`。离线检查既有X2/X3文件不等于重新执行X2/X3，更不产生本轮E4。

## 3. Worker W3 — 最小基准：先裁判，再花模型预算

### 可直接粘贴的目标

【我的推断／设计】读取 `BENCHMARK_MIN.md`，实现一个受控fixture、独立judge、三个权限赛道与一个SmartCLI adapter。不要建通用评测平台，不默认安装或运行全部竞品。首版一个runtime也成立，但不得据此给比较结论。总工程盒≤8小时；模型执行盒≤3小时，单PTY，固定预算，零自动重试。

### 目标文件与上限：7个

| 文件（拟新增者需批准） | 符号／内容 |
|---|---|
| `tools/bench_min/run.py` | validate / judge-selftest / run / report |
| `tools/bench_min/fixture.py` | B1/B2/B3有限状态；受控终端输入与独立结果 |
| `tools/bench_min/judge.py` | task/run/seed校验；不读模型自述判成功 |
| `tools/bench_min/adapters.py` | SmartCLI接入；第二runtime仅明确批准后 |
| `tools/bench_min/schema.json` | 配置、轨迹、结果、来源、费用/预算缺项 |
| `tests/test_bench_min.py` | 评测器负例与权限拒绝 |
| `tests/run_all.py` | 只登记轻量评测器测试，不登记付费/native全矩阵 |

【我的推断／设计】fixture配置、prompt与结果由参数写到获准NEW_RUN，不修改全局模型配置。不得触碰core/vendor/daemon/MCP/pyproject。若Windows原生输入实现需要外部库或新helper，先提案；不得把模拟fixture直接内存调用冒充真实TUI。

### 必须保留与验收

【我的推断／设计】U赛道只暴露终端动作；A赛道追加可列举应用适配；H赛道可用工作文件/API但仍不能改judge私有状态。工具权限由harness执行，不靠prompt劝说。每次episode固定task/track/seed、模型literal id、prompt/schema hash、终端profile与预算。未提供approved spend cap或模型身份不启动网络调用。

【我的推断／设计】裁判先拒绝：假“已保存”、旧run结果、重复非幂等动作、strict-UI越权读文件、quiet伪造ACK、cancel伪造exit。没有这些负例，模型跑出绿色没有价值。输入/结果/输出时间分开，不把Windows重构流要求成source-byte-exact。

【我的推断／设计】新文件创建后：

```text
python -B tests/test_bench_min.py
python -B tools/bench_min/run.py validate --plan <RUN/plan.json>
python -B tools/bench_min/run.py judge-selftest --out <RUN/judge-first.json>
```

【我的推断／设计】只有owner已批准具体模型、费用、平台和single-PTY执行后：

```text
python -B tools/bench_min/run.py run --plan <RUN/plan.json> --out <RUN/episodes>
python -B tools/bench_min/run.py report --from <RUN/episodes> --out <RUN/report.json>
```

【我的推断／设计】默认27个预注册episode，不足条件不临时缩减后声称覆盖完整；第二runtime最多再27个且必须在相同预算内。报告k/n原始结果及失败原因；一次成功就写该例一次通过，不写泛化成功率100%。从未运行的竞品行只写NOT_RUN，无成绩占位。

【我的推断／设计】停止条件：judge可被错误结果骗过；日志缺run_id；清理出现未确认会话；调用预算/费用上限；fixture缺陷；模型ID漂移；权限边界不成立；需要第8个文件或重大依赖。清理失败先停止后续episode，不能为了凑数量继续启动新PTY。

【我的推断／设计】收据拆成 `harness_selftest/E3或工具级`、`native_fixture/E4`、`agent_task/E5`、`distribution/E6`；未做E6就NOT_RUN。若只完成harness，写 `episodes_started=0`、`all_agent_results=NOT_RUN`，不输出随机模拟“成绩”。

## 4. 我与本地结论不一致的地方

| 议题 | 本轮裁决与理由 | 补验/对账，不重跑既有事实 |
|---|---|---|
| “12KiB是预算设计下限” | 【我的推断／设计】拒绝推论。它是某fixture观察到的回压点；每次读更小但频繁服务仍可能足够。单轮预算不等于总缓冲容量 | N1用新增候选、小quantum证明持续推进，不再重跑原X3计数 |
| “optional kwarg因此完全兼容” | 【我的推断／设计】不成立。老caller可兼容，但自定义backend override可能不接受新参数；内部TypeError fallback还会掩盖错误 | S1真实方法+旧签名/主动TypeError负例；无需native |
| “A/B/C合起来7文件，可分别独立回滚” | 【证据支持·E1 + 我的推断】原清单合计9；B依赖预算/pending，C依赖关闭。不能随意回滚下层保留上层 | 对照真实diff计数与依赖，静态审阅即可，不做额外实验 |
| “加cap就改善首帧/CPU，或给child节流” | 【我的推断／设计】cap只控制其所在层，可能只延迟reader；总CPU/首帧收益没有测量。首次read的1.8ms也不是完整parser时间 | N1测候选新增边界；收益无证据则删掉宣传，不增加旧基线实验 |
| “当前Windows路径不能byte-exact” | 【证据支持·E4】接受当前profile的原始输出捕获限制；【我的推断】不推广为所有未来Windows传输都不可能，也不据此说已交付流不必保序 | 只测试本层delivered preservation；不重跑X2寻找原始字节 |
| “T03所有截止边界都已证明” | 【证据支持·E3/E4】给定路径的修复接受；【未确认】连续正数短写跨deadline与select自身抛错是附件代码中的额外路径 | N2窄注入；不重跑256KiB SHA实验，不回退已完成状态 |
| 44 waits/3ms与raw35 waits/2ms | 【证据支持·E4来源冲突】完整接收共同支持，两个数字不可强行合并 | 只用既有run/log归属对账，无法归属则标冲突，不补跑挑数 |
| X3中CPR未回答的独立因果含义 | 【证据支持·E4】接受无pump时未完成、CPR=false与有pump时CPR成功；【我的推断】fixture先写完512KiB才发送查询，无pump停于12KiB，故false本身不能独立证明“已发送查询正等待无人回答” | N1的新候选fixture把一次CPR放在大输出之前，拆开两个因果；不重跑或否定X3 |
| “原型里两observer等于daemon有多watcher” | 【我的推断／设计】拒绝升级。当前是一个长wait内插入快请求，不是两个独立长wait | 保持not-supported标签，S3只验旧interleave不退化 |

【证据支持·E1/E4】以上裁决对应本地proposal/delta、X2/X3、T03closure/raw与当前daemon/backend源码；本轮未将既定测量降格为假设。[^LP][^LPD][^LX2][^LX3][^L03][^L03RAW][^LCB][^LCD]

## 5. 只希望本地补验三项；其他散发方向默认不执行

### N1 — A04候选的新增服务路径与关闭边界

【我的推断／设计】**假设**：S1–S5候选在没有client主动pump、存在fast-job干扰、以及Windows满cap关闭时，仍保留服务机会/数据记账/明确终局。不是重测原来271307或12288这些值。

【我的推断／设计】**方法**：先E3生产方法注入验证budget、pending、interleave与generation；原生获准后，一个新有限fixture由daemon自行服务，测试体禁止代调pump；分别检查POSIX结果+CPR、Windowsdelivered计账+关停状态。新POSIX fixture先发一次CPR再产生有限输出，避免原X3“尚未写完因而尚未发query”的条件混杂；原测量结果不改写。固定较小read quantum，不要求某个单轮必须大于12KiB。fast-job洪泛只在注入/loopback获准环境，原生不做资源耗尽攻击。

【我的推断／设计】**判负**：数据丢/重、budget_limited被标成完整quiet、快请求导致I/O无限饥饿、resize执行污染旧wait、满cap吞掉close、原生超时却报closed。**资源/停止**：每平台最多3种case、每case1会话、≤12秒producer、输出≤1MiB、所有外层监督合计≤120秒；预先批准单次关闭上限。出现未确认清理立即停，不启动下一个case。没有获准监督办法则native NOT_RUN，不去赌阻塞调用会返回。

### N2 — 已完成写入修复之外的调度边缘

【我的推断／设计】**假设**：生产write的“持续少量正进度”和select自身错误仍满足明确deadline/partial-error契约；reply失败不会插入下一逻辑输入造成重复或混字节。

【我的推断／设计】**方法**：只import实际core，注入 `os.write/select/time.monotonic`；每次返回一个正数短写并推进假时钟；另一个case使select抛InterruptedError/OSError；捕获实际written prefix。reply case使用实际session路径+注入backend，保持当前read/feed/reply顺序，不引入新PTY。

【我的推断／设计】**判负**：未写完却跨过deadline继续启动新写、select错误丢失已知前缀、reply整包重发、下一用户输入被插入半个逻辑输入。最后一次write已经完成，不能仅因返回时钟稍晚而改成“未完成”，此控制也须保留。**资源/停止**：≤6个小case，每payload≤4096B，最多1000次注入调用、外层10秒、零原生进程/网络；发现一条真实反例就单独提案，不把它并入A04-S1大改。未执行前仍NOT_RUN，已有T03 E4不受影响。

### N3 — 可信完成的最小E5与错误答案拒绝

【我的推断／设计】**假设**：W2/W3实现能同时让正确有限任务完成、让错误完成证据被拒绝。**方法**：先offline错误证据/judge控制，再按 `BENCHMARK_MIN.md` 固定一个runtime/模型的3任务×3赛道×3seed；不强制第二竞品。

【我的推断／设计】**判负**：任一个预注册错误结果被裁判接受、缺信息却伪造basis、严格UI越权、清理不明还继续运行。任务普通失败照实计入，不自动重跑。**资源/停止**：最多27episodes、单PTY、每episode120秒+清理10秒、3小时执行盒、明确费用上限；任一基础设施/清理/费用边界破坏即停。模型或原生权限不明确时只交离线harness收据，E5 NOT_RUN。

【我的推断／设计】三个实验中的原生或模型部分需要既有明确授权；本文件不是获取权限的替代物。`DIVERGENCE.md`十个方向只是备选，不追加到这三项后“顺便全跑”。

## 6. 下一位 Agent 可直接执行的三步

【我的推断／设计】**第一步：只读对齐。** 读取本文件与A04_PRODUCTION；核对包hash、已有overlay与收据；登记T03数字冲突但不重跑；沿用CodeGraph。提交/读取A04-S1能力与资源提案，列6个文件及批准状态。未批准则本步交接，不偷动源码。

【我的推断／设计】**第二步：只做一个已批准切片。** 从W1-S1或已完成位置的下一片开始，先写该片负例，再实现，按真实物理文件上限与vendor规则验收。只运行受影响回归，不运行旧调查，也不启动全套run_all/真实PTY农场。一个worker完成收据后，下一个worker才能写共享登记文件。

【我的推断／设计】**第三步：将结果转成可拒绝错误的证据。** 派W2做来源/负例核查；W3仅在judge与权限通过后运行N3。每片写 `last.md`、`closure.json`、first-attempt与NOT_RUN，记录下一个唯一任务、残余风险与是否需要批准。下一模型只凭这些文件即可继续，不需要重新推导已经确认的E3/E4。

## 7. 统一交接最小模板（拟定，非执行回执）

【我的推断／设计】任何worker结束时至少填写以下字段；所有placeholder必须替换成实际值或明确unknown，不能把下面示例当完成报告：

```json
{
  "task_or_slice": "<actual>",
  "status": "proposal_only | implemented | verified_in_declared_scope | blocked",
  "base_head": "701e61f6d69aa2420617edf80b1136df8d5e8cf7",
  "base_overlay_sha256": "<actual>",
  "changed_files": [],
  "allowed_max_files": 0,
  "proposal_approval": "<reference or not-approved>",
  "evidence_scope": [],
  "first_attempt": "<path>",
  "negative_controls": "<path or not-run>",
  "accepted_prior_evidence": [],
  "not_run": [],
  "remaining_risks": [],
  "commit": "NOT_CREATED",
  "push": "NOT_REQUESTED",
  "next_single_action": "<actual>"
}
```

【未确认】本轮仅交付设计与worker合同，没有执行任何产品测试、模型任务、原生测量或发布动作。不能把本文的命令清单转换为已运行列表。


---
## 来源定位

[^L00]: 附件 `SmartCLI_v3_Upload/README_FIRST.md`，事实基线摘要、Owner 提醒。E1/E3/E4 分别标注；HEAD 仍是基线，但本轮实现位于未提交工作树。收到并阅读：2026-09-16。

[^L03]: 附件 `SmartCLI_v3_Upload/03_receipts/T03_closure.json`，first_results、mutation_cycle、claim。E3 注入 + E4 本机 POSIX library；叙述 44 次等待。收到并阅读：2026-09-16。

[^L03RAW]: 附件 `SmartCLI_v3_Upload/02_evidence/T03_posix_real_pty.json`，planned_bytes、writability_waits、child_report。E4 原始收据；此文件记录 35 次等待，与摘要 44 未消歧，不改写任何一方。收到并阅读：2026-09-16。

[^LCB]: 附件 `SmartCLI_v3_Upload/04_code/pty_backend.py_T03_implemented.py`，PtyBackend、WinptyBackend._read_loop/read_nonblocking/terminate、PosixPtyBackend.write。E1 本轮实现源码，T03 已落地；不以远端旧代码覆盖。收到并阅读：2026-09-16。

[^LCD]: 附件 `SmartCLI_v3_Upload/04_code/tui.py_CURRENT_daemon_A04_target.py`，_serve_forever、worker、INTERLEAVE_OK、_drain_interleavable、_reply、_snapshot_response、cmd_close。E1 当前 daemon 源码；既有 interleave/resize 排除必须保留。收到并阅读：2026-09-16。

[^LCPKG]: 附件 `SmartCLI_v3_Upload/04_code/pyproject.toml`，tool.setuptools.package-dir、project.scripts。E1 smartcli_drive 指向 skills/drive-tui/scripts；改脚本也是改发行路径。收到并阅读：2026-09-16。

[^LP]: 附件 `SmartCLI_v3_Upload/03_receipts/A04P_PROPOSAL.md`，§2 三切片、§3 未修项、§4 验收。提案不是实现证明；局部论断 E1/推断，数字引用 LX2/LX3。收到并阅读：2026-09-16。

[^LPD]: 附件 `SmartCLI_v3_Upload/03_receipts/A04P_DESIGN_DELTA.md`，§1 模型边界、§2 符号、§3 文件清单。E2 原型结论；不是产品实现。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

