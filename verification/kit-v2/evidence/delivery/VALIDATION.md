# 本次交付验证记录
交付日期2026-09-16（Asia/Tokyo）。本节记录**执行过什么**，而不是待办门禁。

## 实际结果
| 检查 | 结果 | 能证明／不能证明 |
|---|---|---|
| 新交付工具与参考模型 unittest | **62 total / 62 passed / 0 skipped / 0 failures / 0 errors** | 仅工具及E2注入模型；不是SmartCLI产品通过 |
| 本轮初次工具测试 | 60/60，通过 | 初次日志保留；后来增加2项边界检查，不是失败自动重跑 |
| 新写Python语法解析 | 10文件，PASS | ast.parse，不等于实际core接口已测试 |
| v1原ZIP内清单 | 49/49一致 | 只校验旧包完整性，没有在这里重跑它的47项测试 |
| 选取的任务附件与PROMPTS.zip | 19份，逐字节一致 | 不转发与SmartCLI无关的live harness配置 |
| 单独上传MD与ZIP内MD | 逐字节一致 | 本地E3报告保持原文 |
| 新产品回归模板／C0 real-core runner对SmartCLI | **NOT_RUN** | 本执行容器未安装pyte；不把缺依赖当失败复现或成功 |
| SmartCLI真实PTY、ConPTY、daemon loopback | **NOT_RUN** | 不宣称A01/A04/A05/A06实机验证 |
| 竞品运行、性能或模型成功率 | **NOT_RUN** | 仅重读官方文档/指定源码 |
| 离线页面结构、搜索、移动端布局 | **PASS（内存HTML渲染）** | 17章节；50链接路径/锚点检查；390px无整页溢出；不包含file://导航测试 |
| 用户本地库、HEAD、全局设置 | **未修改** | 新文件只在本次交付工作目录 |

最终工具测试命令（本次容器使用独立工作临时目录）：
```sh
SMARTCLI_V2_TEST_TMP=/mnt/data/smartcli_v2_work python -B -m unittest discover -s tests -v
```
本轮为Linux、Python 3.13.5；不是用户Windows机器。详情见`provenance.json`、`tool-tests-final-62.log`。不要将这里0 skip反推为Windows symlink测试也会通过；本地账号不允许symlink时该一项明确SKIP，报告total/pass/skip。

## 回归模板的状态
`tests_product/test_cell_span_regression.py`有9个test方法；SGR模板有5个；短写模板有2个。它们是交给本地的**候选回归文件**，均未在此容器对真实core执行；需要本地红绿红与现有门禁。T04模板尚需worker在同文件增加溢出/字符串负载的实现相关断言，T03也需增加deadline/cancel错误对象断言。

实际小runner覆盖SCREEN、SGR、INPUT、WAIT、REJECT五类。只有INPUT使用真实生产方法上的注入OS；没有原生fd/PTY。标准库runner测试使用故意缺依赖的fixture，证明NOT_RUN不被当成PASS，**不是导入真实SmartCLI**。

## 参考模型边界
字节偏移、EAGAIN/EINTR、partial取消、真实错误对象、byte cap和close请求/EOF分离可被E2模型测试。模型没有原生线程/Condition/socket，不能证明线程被唤醒、RSS上界、全双工进度或close不会卡死。close请求后仍允许最终输出，只有EOF及排空才进入drained；这也不等于进程exit。

## 可用性限制与真实性
尝试通过容器网络获取缺失依赖没有成功，因此没有安装或补造pyte结果；网上文档可通过专用浏览工具读取，不代表本地执行容器有网络。没有让这些限制阻止交付设计、标准库工具和已提供的本地证据。

工具不是sandbox。审查代码并显式consent后，Python代码仍拥有执行用户权限；范围守卫不覆盖repo外或gitignored路径。C0超时回收的是自己的直接子进程，不构成任意进程树隔离。禁止用于未知不可信仓库后宣称安全隔离。

## 页面验证边界
专用Playwright浏览器未预装，改用已存在的系统Chromium；系统政策禁止file://导航，没有改变该政策。生成的HTML通过内存set_content完成渲染、搜索、空结果/清除、移动端宽度检查；相对下载链接用路径/锚点静态检查，未在浏览器执行文件导航。初次环境失败记录和最终验证记录分别保留在browser-initial-attempt.json及browser-check.json。

## 清单与最终ZIP
最终文件冻结后生成MANIFEST.json，再从目录和最终ZIP各验证一次；核验结果随外部交付回执提供，避免把“最终ZIP的hash”循环嵌入ZIP本身。所有metadata、YAML、页面与Python均纳入；仅忽略解释器缓存。外部`.zip.sha256`用于校验最终压缩包，SHA256不提供发行者数字签名。

用户提及web-chat-archive元数据失配属收到的事故报告；原ZIP未提供，所以本轮未修复、未重新签名，也不会以“只是元数据”为理由忽略它。新校验器的YAML篡改负例确实在本轮执行。
