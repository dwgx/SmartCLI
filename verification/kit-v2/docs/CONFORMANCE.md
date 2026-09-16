# CONFORMANCE — 陌生人可跑的“可信交互”小套件
**目标：已有Python+pyte环境中，审阅后用一条命令完成少量确定性检查，运行预算远小于5分钟。** 五分钟不是安装依赖、配置系统或所有硬件的实测保证。不得为满足这个标题跳过失败项。

## 1. 两种证据，不混成一个绿勾
`C0/memory` 是本包实际提供的 runner：导入指定repo的真实core，无PTY、无socket、无网络、无LLM；INPUT以fake OS接收器调用真实POSIX backend。可在Windows检查逻辑，但不能证明Windows任意byte输入或真实POSIX吞吐。

`C1/native` 是本规格要求、尚未提供运行器且未执行的后续小型验证：一个真实PTY/ConPTY，有明确许可，串行、有限payload、独立child裁判。当前命令不自动启动它。`E4 NOT_RUN`不能被C0通过掩盖。

## 2. 实际命令
```powershell
$Kit = 'D:\Project\SmartCLI-v2-handoff'
$Repo = 'D:\Project\SmartCLI'
$Python = 'D:\Software\Developer\Python314\python.exe'
& $Python -B "$Kit\tools\verify_bundle.py"
& $Python -B "$Kit\tools\conformance.py" --repo $Repo --consent-execute-reviewed-code
```
用`--case screen|sgr|input|wait|reject|all`限制单项。选case不代表整体通过；报告注明selected_cases。每case独立子进程，默认15s截止、256KiB输出上限，不自动重跑。导入前须审阅当前源码，这不是sandbox。

不写文件是默认。`--out`要求显式路径和已存在父目录，拒绝覆盖已有报告、拒绝写入目标repo/本包。报告不包含用户真实终端日志或环境变量值。

## 3. 四个必要场景 + 一个SGR补充
| ID | 动作与oracle | 必須输出 |
|---|---|---|
| SCREEN | 输入真实中文菜单，第二项反色；独立字面量`保存` | expected、selected.text、span、PASS/FAIL |
| INPUT | 真实PosixPtyBackend.write配短写/EAGAIN/EINTR接收器 | planned/received字节数、SHA256、call count、异常、`io_mode=injected_os` |
| WAIT | 真实readiness等待`READY`；匹配后返回MARKER | reason、basis=`rendered_text_regex`、`basis_origin=conformance_adapter`、claim_scope=`state_matches_only` |
| REJECT | 屏幕只有反色`3`，要求`保存`；匹配不得成功 | expected、actual、matched=false、`negative_control=REJECTED` |
| SGR | 每切点/逐字节/固定随机分片，独立RGB/underline语义 | payload/cuts/control count、首个差异、属性断言、feed_errors |

等待basis由此小runner根据旧接口reason明确标注，**不冒充旧SmartCLI已经输出该新字段**。REJECT证明文字条件不满足，不冒充daemon的鉴权拒绝。只有C1或以后协议集成测试才验证产品真实wire响应。

一个正确拒绝本身是测试PASS。相反，缺依赖、import异常、超时、输出超限是NOT_RUN/ERROR，不是“发现正确错误”。SCREEN的业务断言失败，不能伪装成环境未就绪。

## 4. 机器输出契约
每项一条JSON记录，最终一条summary。示意，不是实测：
```json
{"case":"screen","status":"FAIL","evidence":"E3-memory","expected":"保存","actual":"3"}
{"case":"input","status":"FAIL","io_mode":"injected_os","received_bytes":2,"planned_bytes":16,"native_pty":"NOT_RUN"}
{"case":"wait","status":"PASS","reason":"MARKER","basis":"rendered_text_regex","basis_origin":"conformance_adapter","claim_scope":"state_matches_only"}
{"case":"reject","status":"PASS","matched":false,"negative_control":"REJECTED"}
```
总报告必须有Python、pyte、实际模块文件路径/指纹、基线或UNKNOWN、各case结果、native_pty=NOT_RUN、首次退出码、是否重跑（固定false）。不把“MARKER”翻译成命令成功，不把输入sha匹配翻译成业务验证通过。

退出码：0=所选case全PASS；1=一个或多个契约FAIL；2=NOT_RUN/ERROR/参数错误。NOT_RUN存在时即使另有FAIL，summary也返回2且保留FAIL列表。选择screen通过不会打印ALL_CONFORMANCE_PASS。

## 5. C1/native 的小规模规格（需单独获批）
不运行vim/htop，不开浏览器。只运行一个自有Python fixture：进入明确terminal mode，打印菜单/nonce；读取限定输入；返回实际接收长度/hash；最后发完成marker并退出。最大输入4KiB、总输出64KiB、整个会话≤15s、一次一个、finally只关闭自己的句柄。

POSIX的原始字节输入需raw/no-echo，防止行规程更改NUL/CR/LF；Windows用明确UTF-8文本profile，不宣称二进制透明。屏幕输出可能有终端回写/换行差异，比较按profile定义的语义cells，不能跨平台直接比较所有wire bytes。

必须还有一个假答案：发错nonce或错hash，等待不能通过。marker不是进程exit的替代；确认child exit和filesystem/return-code独立裁判，各自打印。若不支持可信command boundary，明确`command_finished=UNSUPPORTED`。

## 6. 反作弊与兼容
对照在同fixture、同裁判、同预算。输出不只是SUCCESS一词。禁止将随机40-seed率当发布门槛或调低阈值；本小套件不依赖真实桌面、token或模型服务。

测试不修改用户文件，不调用cleanup-all。故障注入只在case自己的进程中修改os.write/select，结束自动隔离，不改仓库源码。候选实现若不再通过这些注入点，报适配失败并更新fixture审查，不许跳过INPUT来换绿。
