# EVIDENCE_STANDARD — 陌生人能复核、错误答案会被拒绝的可信交互标准

> **标签与状态**：`【证据支持·E1…E6】` 表示来源支持的事实；`【我的推断／设计】` 表示本轮建议、约束或逻辑推导；`【未确认】` 表示不能据现有材料下结论。标题、命令块和表格继承其紧邻的标签；表格有状态列时以该列为准。任何“拟新增”符号、参数、命令都尚未实现。外部来源访问日统一为 **2026-09-16**；固定提交只代表该快照，不称“最新”。本轮只读附件与一手资料，未运行 SmartCLI、终端、竞品或测量脚本。


## 1. 标准的对象：一个有边界的主张，而不是一个绿色徽章

【我的推断／设计】“可信交互”应表示：在声明的平台、后端、观察表示和操作范围内，结果有可核查依据；缺少依据时返回未知、部分完成或明确失败。这里定义两种互不冒充的产品入口：**离线证据核查**不运行被测程序；**现场一致性检查**执行获准的实际产品路径。五分钟是预装依赖、已有证据包条件下的验收资源上限，不是安装耗时保证，更不是本轮实测。

【证据支持·E1】现有 `05_verification/conformance.py` 支持 `screen/sgr/input/wait/reject/all`，读取真实 core；其中 `wait` 的完成依据由 conformance adapter 解释。它没有覆盖真实 daemon 取消、完整回放或发行安装。不能将已有 `--case all` 改名为“全能力认证”，也不能把 adapter 注释当成 runtime 自己返回的依据。[^LCONF]

【我的推断／设计】证据等级是**作用域**而非自动升级的勋章：

| 等级 | 可以证明 | 不能自动证明 |
|---|---|---|
| E1 | 固定源码／规范存在某条路径或契约 | 实机运行、时延、版本实际可安装 |
| E2 | 参考模型和明确假设下的性质 | 生产符号调用正确、原生 I/O 正常 |
| E3 | 真实 core 在指定内存／注入条件中的行为 | 原生调度、ConPTY 投递、daemon 闭环 |
| E4 | 指定本机终端／容器上的实际路径 | Agent 独立完成任务、其他平台等价 |
| E5 | 指定 Agent、工具权限与独立裁判下的任务结果 | 大样本成功率、所有任务或模型 |
| E6 | 精确发行物在干净安装条件中的契约 | 同版本不同构建、未来更新的可靠性 |

【我的推断／设计】记录应同时带 `status` 与 `evidence_level`。`PASS/E4`、`NOT_RUN`、`UNSUPPORTED`、`BLOCKED`、`INVALID_EVIDENCE` 必须可区分。某 profile 的必需项缺失，整个 profile 不得 PASS；可报告已通过的子项，但不得通过缩小分母隐藏缺项。来源收据已证明的实验保留为 `ACCEPTED_PRIOR_EVIDENCE`，不重新执行或变成本轮测试次数。

## 2. 证据包最低内容与来源防混淆

【我的推断／设计】一个证据目录至少含下列产物。它可以先用标准库 JSON／JSONL 实现，无需数据库或遥测服务。这里的名字是**拟新增输出契约**，不是声称附件已经全部具备。

| 产物 | 必须包含 | 被解决的真实失败 |
|---|---|---|
| `manifest.json` | 相对路径、长度、SHA256、schema；校验 manifest 内文件及额外文件；拒绝越界、符号链接替换、重复路径 | 元数据与 ZIP 清单不一致仍被当成完整包 |
| `run.json` | HEAD、**工作树 overlay 指纹**、实际导入路径、canonical/vendor 指纹、Python/pyte/pywinpty/wcwidth、OS build、backend/profile、终端尺寸、时钟口径 | HEAD 未变但 T03/T04/T05 已修改，版本号掩盖真实代码 |
| `fixture.json` | 固定输入或生成器 hash、seed、资源上限、终止条件、工具权限 | 只有截图或叙述，无法知道程序应该怎样响应 |
| `events.jsonl` | 有序事件、generation、action_id、read/fed offset 与 frame revision、输入进度、关闭/取消事件；来源明确 | 将排队、已写、已接受、已完成混成一种事件 |
| `observations.jsonl` | 原始 runtime 响应、表示层、局部 pending、上游可知性、截断、解析异常；与 event revision 关联 | unread 被误叫 idle，ConPTY 合成流被误叫原始输出 |
| `judge.json` | 裁判版本、任务预期、实际读取的独立证据、裁判结果；Agent 无写权限 | Agent 自己声明成功后自己生成一个成功证书 |
| `negative_controls.json` | 错误输入／伪造结果是否确实被拒绝，拒绝原因与实际退出码 | 测试只证明能输出 PASS，没有证明能发现错 |
| `first_attempt.json` | 第一轮原始返回码、超时、输出上限、清理结果，不能被重跑覆盖 | 重试后绿色覆盖首次失败 |
| `coverage.json` | 各平台、各层、各 profile 的 PASS/NOT_RUN/UNSUPPORTED 与原因 | E3 冒充 E4，库级冒充 daemon 或 wheel |
| `README_REVIEW.md` | 三条核查命令、预期判据、秘密/删改声明、证据不能支持的结论 | 陌生人需要读完整聊天才能知道怎么审阅 |

【我的推断／设计】来源字段至少分为 `runtime`、`harness`、`application_adapter`、`independent_judge`、`model_claim`。保存 runtime 原始响应，再生成解释；解释不能反向填回原始响应。`completion_basis_origin="harness"` 时，只能证明 harness 使用了某种规则，不能声称 SmartCLI 公共 API 已提供该字段。

【我的推断／设计】SHA256 用于检测包内修改，不证明作者身份，也不阻止攻击者同时改数据与自签清单。对于对抗性验证，裁判应置于 Agent 无写权限的环境，外部保存原始 manifest hash；普通本地 smoke 必须明确只验证非对抗条件。含秘密的原始流默认不外传；脱敏版与原版分别 hash，脱敏后不得宣称字节完全回放。

## 3. 每次交互必须打印的事实轴

【我的推断／设计】采用以下拟定报告结构。值为枚举或 null；不能由成功退出码自动补全。缺少产品字段时可在报告中标记 `unavailable`，但不得伪造实际 runtime 能力。

```json
{
  "run_id": "<actual-run>",
  "generation": "<actual-generation>",
  "representation": "posix_pty_stream | conpty_reconstructed_utf8",
  "input": {
    "action_id": "<actual-action>",
    "accepted_by_runtime": true,
    "written_bytes": null,
    "total_bytes": null,
    "completion": "written | partial | unknown | not_attempted",
    "application_ack": "unknown | accepted | ignored",
    "basis_origin": "runtime"
  },
  "observation": {
    "revision": "<actual-revision>",
    "pending_known_bytes": null,
    "upstream_pending": "unknown",
    "local_cut": "drained | budget_limited | unknown | error",
    "parser_partial": null,
    "truncated": false
  },
  "wait": {
    "outcome": "matched | quiet | timeout | cancelled | failed | unavailable",
    "basis": "observed_predicate | local_quiet | app_ack | process_exit | unknown",
    "basis_origin": "runtime | harness | application_adapter"
  },
  "close": {
    "state": "not_requested | closing | closed_confirmed | close_unconfirmed",
    "process_exit_observed": false,
    "reader_eof_observed": false
  },
  "verification": {
    "status": "not_run | passed | failed",
    "basis_origin": "independent_judge"
  }
}
```

【我的推断／设计】`written` 不等于应用 ACK，应用 ACK 不等于目标文件或业务结果正确。`quiet` 是观察条件，不能默认成 `command_finished`。取消只结束特定等待或尚未开始的工作，不能抹掉已写的前缀。关闭响应必须区分“已接收关闭请求”和“进程／读端确实收敛”。不得为了保持旧 `ok` 字段就隐去 `close_unconfirmed`。

【证据支持·E1】MCP 普通请求的取消通知与任务增强请求的取消方式不同；取消还可能遇到已经完成的请求。该规范不能提供终端字节或外部副作用回滚。[^S16]

【证据支持·E4】Windows 附件记录的是当前 ConPTY 路径的重构输出，不能用“收到输出总字节数等于子进程原始 stdout 字节数”作为该 profile 的承诺。[^LX2]

【我的推断／设计】Windows 的输入验收可以由受控应用在独立结果文件中报告实际接收内容与摘要；这是应用输入见证，不是原始输出逐字节等价。POSIX 的原始字节对比也需声明 raw/canonical mode、echo、换行处理等配置，不能只写“POSIX 都 byte-exact”。

## 4. 六条必须同时有正例与负例的验收轴

【我的推断／设计】下面是验收设计；已给出的 T03/T04/T05 收据直接引用。只有修改了相关路径，才运行改动所需的回归，而不是重跑历史测量。

| 轴 | 正例与正确性来源 | 必须拒绝的错误答案 | 层级与缺口 |
|---|---|---|---|
| 观察正确 | 固定 cell fixture 的原始 cell 与选中 span；跨分片 SGR 的独立预期属性 | 将选中项改成 `3`；把 ff0080 换成错误颜色；正文正确但 selected 错也必须 FAIL | T05/T04 已有 E3；native 表示一致性按平台另列 |
| 输入不丢不重 | 生产 `write` 的注入序列与预期字节串；原生 profile 用子进程独立 length/hash 或 action ledger | 短写后返回成功；重发整个 payload；结果 hash 正确却复用另一 run 的报告 | T03 已有 E3/E4；不是全部平台／daemon 完成证明 |
| 完成依据可信 | runtime 的 observed/matched/quiet、应用 ACK、独立结果明确分列 | 旧 READY、仅 budget exhausted、缺 ACK 却填 accepted、安静却填 process_exit | 新 pending 与来源契约尚需实现 |
| 失败可诊断 | 首次错误、最后 observation、写入偏移、队列/解析状态与原始异常保存 | 只说 timeout 而覆盖 partial；feed_errors 为零就宣布无损 | 需要以当前实际工具响应验证 |
| 取消可收敛 | 取消指定 waiter 后，其他观察可继续；已写前缀保留；关闭未知明确返回 | cancel ACK 伪装成 child dead；timeout 后自动重发输入；满队列吞掉关闭状态 | 当前 conformance 不覆盖；缺项不得总 PASS |
| 证据可复核 | manifest、同一 profile 下离线重放派生观察、独立裁判 | 改 YAML/参数未改清单；丢事件后继续声称连续；generation 不符仍拼接 | 新 verifier 可以离线先实现；生产 replay 未具备则 NOT_RUN |

【我的推断／设计】每个负例检查的是“被测实现／证据验证器返回拒绝”，不是在外层 test 中直接写 `assert bad != good`。例如先创建错误 selected 的证据副本，再调用真正 verifier，断言退出非零且 reason 指向选中标签矛盾。否则只是测试作者知道正确答案，没有测试系统能够拒绝错误答案。

【我的推断／设计】已完成增量的 mutation 收据保持原有测试 hash 与四阶段结果。新 A04 回归也使用隔离副本中的针对性回退，不碰用户原工作树；变异必须命中生产实现符号，不能再次误改抽象基类后把“没有失败”解释为修复无价值。[^L03]

## 5. 五分钟核查的两个 profile

### 5.1 离线 `review`：可以先交付，绝不偷偷执行证据包

【我的推断／设计】拟新增 `verify_evidence.py` 的 `review` 模式只用标准库读取 JSON/JSONL、hash 和判据，不 import 包内 Python，不启动 shell，不读取未列明文件。资源上限建议：60 秒核查、64 MiB 证据总量、单文件8 MiB、最大100000条记录；这是初版硬停预算，不是性能测量。超过上限报 `REVIEW_BUDGET_EXCEEDED`，不假装 PASS。

【我的推断／设计】以下三条为**待 W2 实现后**可用的目标命令；本包只有规格，没有新增该工具：

```text
python -B verify_evidence.py review --bundle <EVIDENCE_DIR>
python -B verify_evidence.py reject-controls --bundle <EVIDENCE_DIR> --out <NEW_RUN/negative.json>
python -B verify_evidence.py explain --bundle <EVIDENCE_DIR>
```

【我的推断／设计】第一条核查文件与事实一致性；第二条对隔离副本施加列明错误并确认拒绝；第三条必须打印证据级别、完成依据、来源、缺项、清理状态。三条完成只是 `PASS_REVIEW`，不升格为这台电脑已运行原生终端，也不证明历史证据的作者身份。

### 5.2 现场 `core-smoke` 与可选 `native-smoke`

【证据支持·E1】现有工具可直接使用以下参数形式；`--out` 必须指向新文件且在 repo／工具目录之外，`--consent-execute-reviewed-code` 是明确执行许可。[^LCONF]

```text
python -B <VERIFICATION_ROOT>/conformance.py --repo <REPO> --case all --consent-execute-reviewed-code --out <NEW_RUN/core-first.json>
```

【我的推断／设计】对本轮已确认的 core，不要求重跑这条历史检查。下一位陌生人或新发行物可以使用它理解现有范围；输出只能说五类已覆盖 case 的结果。W2 加固后可提供 `--profile credible-v1`，但在新增取消／证据拒绝项前，这个 profile 必须 `UNSUPPORTED`，不能落回 `all` 后伪装完成。

【我的推断／设计】未来 `native-smoke` 在预装当前产品、获准单会话后，运行一个有限输出的小 fixture：产生唯一 run marker → 等待字面输入 → 产生独立结果 → 保持一个可取消的等待 → 确认关闭或报告未确认。总预算300秒、单会话、子进程输出≤256 KiB、工具日志≤8 MiB；取消／关闭分别预注册硬停上限。实际阈值需先由 owner 批准，失败时不得临时放宽。不得默认调 Docker、WSL、管理员权限或外网。

【我的推断／设计】任务真实结果由独立 fixture judge 读取文件或私有控制接口；这些 judge 权限不暴露给严格 UI 赛道的 Agent。若当前产品没有相应取消接口，不用 `kill` 伪造“取消 waiter 已实现”：报告不支持，按 profile 判失败或未完成。

## 6. 回放的三种含义必须分开

【我的推断／设计】`evidence_review` 是核查产物；`observation_replay` 是从记录的 delivered-stream 与同一解析 profile 重算观察；`live_reexecution` 是重新启动目标程序。它们不是同一实验。本轮禁止为了补一份 replay 收据而重新执行已给出的 E4。

【我的推断／设计】checkpoint 最少需要 parser/profile、尺寸、主备屏与模式、光标/样式、累计 fed revision、流过滤器状态和未完成 UTF-8 解码状态。只保存 screen 文本无法在半个 SGR 或半个 Unicode 字符后恢复。暂时不能安全序列化完整状态时，从已知初始状态重放短 trace，而不是使用不可信 pickle。ConPTY replay 只复现捕获到的重构 VT，不能恢复上游已经未交付的历史。

## 7. 本轮资料中的证据对账，不制造新的实验

【证据支持·E4】T03 raw JSON 记录35次可写等待、0.002秒；T03 closure 的叙述记录44次、3ms。二者都记载262144字节完整接收与正确 SHA，但附件没有共同 run_id 来证明是同一次运行。接受其共同支持的完整写入结果，分别保留次数/耗时，不选较好数字、不求平均。[^L03][^L03RAW]

【我的推断／设计】将上述记录为 `provenance_conflict`，由本地对照**已有日志与文件时间**归属，不要求重跑。后续每条数值必须指向原始产物、run_id、字段和计时区间；无法归属就不用于性能比较。

【证据支持·E4】X2 的1.8ms对应读取/拼接返回301763字节，不包含随后 pyte feed、快照和响应的完整耗时；X3 的child与parent耗时字段也不同。[^LX2][^LX3]

【我的推断／设计】报告不得把上述值称为“解析尾延迟”。旧实现没有收到完整子进程报告，也不等于一个字节都未进入内核或子进程。历史 `NOT_RUN` 与同包更新后的 E4 closure 冲突时保留原文，采用明确更新收据表达当前覆盖，不把旧缺项重新变成实验要求。

【证据支持·E1／附件格式】`02_evidence/X3_posix_idle.json` 包含两个连续的顶层JSON对象，而非一个JSON数组。保留原始文件字节；读取器应由明确的格式声明按连续对象解码，并为每个对象保留字节范围与case。不能因单次 `json.load` 报“extra data”就判E4无效，也不能静默重排或改写原件使其符合新schema。新生成的证据一律使用明确定义的JSON或JSONL格式。[^LX3]

## 8. 本标准的交付判据

【我的推断／设计】一个可对外称为 `credible-v1` 的结果，必须同时满足：声明的六轴均有真实路径正例；每轴至少一个错误答案经实际 verifier/产品路径拒绝；平台、导入来源、表示层和执行层完整；来源无法冒充；第一轮失败不被覆盖；取消和关闭有终局或未确认；未知项使总体声明收窄。只有 core-smoke，通过范围就仅是 core-smoke。

【未确认】本轮没有运行上述新 profile、验证器、原生 fixture 或回放。它们的命令、资源上限与输出结构是给本地 W2 的实施合同；不是一个已经测出的“五分钟成绩”。


---
## 来源定位

[^L03]: 附件 `SmartCLI_v3_Upload/03_receipts/T03_closure.json`，first_results、mutation_cycle、claim。E3 注入 + E4 本机 POSIX library；叙述 44 次等待。收到并阅读：2026-09-16。

[^L03RAW]: 附件 `SmartCLI_v3_Upload/02_evidence/T03_posix_real_pty.json`，planned_bytes、writability_waits、child_report。E4 原始收据；此文件记录 35 次等待，与摘要 44 未消歧，不改写任何一方。收到并阅读：2026-09-16。

[^LCONF]: 附件 `SmartCLI_v3_Upload/05_verification/conformance.py`，run_case wait/reject、run_bounded、main、fingerprint。E1 现有 C0 runner；不覆盖六维全部能力，不能宣称新参数已实现。收到并阅读：2026-09-16。

[^LX2]: 附件 `SmartCLI_v3_Upload/02_evidence/X2_windows_conpty.md`，§1–3、NOT_RUN；另见 X2_steady_queue.json/X2_burst_delivery.json。E4 固定环境测量；不推广成所有 Windows 负载的故障率。收到并阅读：2026-09-16。

[^LX3]: 附件 `SmartCLI_v3_Upload/02_evidence/X3_posix_idle.md`，Fixture、Results A/B、What this establishes；另见 X3_posix_idle.json。E4 已复核；0.926 为 child seconds，0.957 为 parent elapsed，勿混用。收到并阅读：2026-09-16。

[^S16]: 【证据支持·E1】[MCP：Cancellation，2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)。E1 固定规范版本；取消通知/竞争及 task 请求的取消边界。访问：2026-09-16。

