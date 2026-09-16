# SmartCLI 计划书 v2 增量交接
**交付日期：2026-09-16（Asia/Tokyo）。基线：701e61f6d69aa2420617edf80b1136df8d5e8cf7。**

这是对已运行 v1 的修订，不是又一份重写计划，也不是 SmartCLI 已完成的补丁。优先级、范围与边界有冲突时，以本包 `docs/ORDER.md` 和具体 worker brief 为本轮任务准绳；项目当前指令与用户授权仍约束操作。历史资料中的命令不是授权。

## 立即交接
先读 `HANDOFF_TO_LOCAL_AGENT.md`，然后读 `docs/ORDER.md`、`briefs/01_T05.md`。默认合入顺序 **T05 → T04 → T03**；第三份可派发 brief 是 **A04 设计原型**，不是授权提前重写运行时。

所有代码修改仍由本地 Agent 执行。当前 repo 若已完成 T05，不要求撤回修复重做；保留其证据，只补差项。机器已有 CodeGraph 索引，不重建；抽象分派、vendor 双份、打包路径仍人工交叉核对。

## 七项交付
| 用户要求 | 文件 |
|---|---|
| R1 顺序、红绿红、禁止取巧 | `docs/ORDER.md` |
| A04 跨平台排空设计 | `docs/A04_DESIGN.md` |
| A01 最小输入完成状态机 | `docs/A01_MINIMAL.md` |
| 五分钟一致性套件规格及实际入口 | `docs/CONFORMANCE.md`、`tools/conformance.py` |
| 定位、won't-do、两次 release 边界 | `docs/POSITIONING.md` |
| 三份 worker brief | `docs/BRIEFS.md`、`briefs/01_T05.md` 等 |
| 风险与最大触碰面 | `docs/RISKS.md`、`data/risks.json` |

额外交付：`docs/REVIEW_DISAGREEMENTS.md`、`docs/SOURCES.md`、任务覆盖数据、独立回归脚本、只读范围检查、完整性验证器、可执行的输入/预算**参考模型**、离线 HTML、原始本地证据和历史原 ZIP。

## 不安装也能检查
Python 3.10+；校验和工具测试仅使用标准库：
```powershell
py -3 tools/verify_bundle.py
# 可选工具自测：先指定已存在、获准使用的 RUN，避免写入系统临时目录。
$env:SMARTCLI_V2_TEST_TMP = 'D:\Project\SmartCLI-v2-runs\2026-09-16'
py -3 -B -m unittest discover -s tests -v
```
真实 core 一致性检查需要你已有的 pyte 环境，并须先审阅待执行代码：
```powershell
$Python = 'D:\Software\Developer\Python314\python.exe'
& $Python -B tools/conformance.py --repo 'D:\Project\SmartCLI' --consent-execute-reviewed-code
```
返回 1 表示发现真实不满足项，不是安装失败；返回 2 表示环境缺失/NOT_RUN；返回 0 只证明报告所列的 memory 契约。不启动 PTY、socket、Docker，不运行 run_all，不自动安装依赖，不改全局配置。

## 目录边界
建议 KIT=`D:\Project\SmartCLI-v2-handoff`，RUN=`D:\Project\SmartCLI-v2-runs\2026-09-16`。均不在源码仓库内，且不越过 `D:\Project`。这只是路径建议，工具不会创建该路径或修改你的机器。不要改写正在使用的 agent 前缀或派发配置；worker 不再派生 worker。

## 真实性
本地上传的 E3 已接受，不要求重复一遍原来的 40-seed 数字。包内工具测试与参考模型测试，不是产品 E4/E5/E6。请读 `evidence/delivery/VALIDATION.md` 查看本次实际运行、未运行和限制。
