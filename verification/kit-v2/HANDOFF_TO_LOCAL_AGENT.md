# 给本地主 Agent：v2 接收与继续工作
这是执行交接，不是要求再次做全项目调研。先使用你已有的CodeGraph和本地E3报告。不要重建索引、不要重跑40-seed统计、不要重写活跃prefix或全局配置。

## 三步
**第一步：接收而不覆盖。** 将完整包放在`D:\Project\SmartCLI-v2-handoff`或你已获准的等价位置；校验`tools/verify_bundle.py`。读取`docs/ORDER.md`及`docs/REVIEW_DISAGREEMENTS.md`，确认当前HEAD/工作树及有无另一个writer。新证据优先，但必须保留旧基线原字节。v1的state.json不自动迁移，旧`next`建议不得覆盖v2顺序。

**第二步：直接完成一个闭环。** 按`briefs/01_T05.md`在同一会话做T05；若另一个Agent已经修好，收据与测试足够就记录accepted-existing，不再修改。只动允许的三文件，先红再绿，再在隔离验证副本回退修复证明红，恢复绿。同步仅那一个vendor孪生，不盲运行会删除整个目录的sync_vendor.refresh。

**第三步：续接而非重启。** 记录`RUN/T05/last.md`和`templates/CLOSURE_V2.json`相同结构的收据；控制组、NOT_RUN和源码hash齐全。然后顺序进入T04；T03注入式逻辑可设计，真实POSIX门保持open；A04原型按第三份brief单列，不把它混成运行时大改。

## 自主范围
实现办法可以更好，停止条件不能弱化。允许把不适用旧结论refute并附证据，允许在既定文件范围内补针对性测试。超过范围、新线程/队列/公开API/重大依赖要先提交小提案；不能自己把文件allowlist扩大后宣布审核通过。

本轮没有授权commit/push/release、重型PTY、Docker服务启动、安装新全局依赖或派生worker。若Owner之后明确授权，按当前规则记录后执行；不要用本交接替代权限。对已授权的T05/T04小范围修改，不必每改一行再询问。

## 目录/工具注意
KIT和RUN都在`D:\Project`内，但不放进源码仓库。报告路径由你显式创建；工具不会部署Skill或改注册表。运行自测若需临时目录，设置本次进程的`SMARTCLI_V2_TEST_TMP`到获准RUN（非持久配置），不要修改harness配置。

`scope_guard capture`在每个worker开始时记录工作文件基线，`check`比较该worker的新改动；这允许上一个未commit的已验收修复留在树上，不把它误报为本worker越界。它不是沙箱，不能发现repo外或gitignored文件改动，仍需本人守界。

## 最大三项补验
见`docs/REVIEW_DISAGREEMENTS.md`末尾X1/X2/X3。X1可先注入式内存；X2/X3真实环境另获批且一次一个PTY。不要新增第四个重型实验来弥补不确定性。
