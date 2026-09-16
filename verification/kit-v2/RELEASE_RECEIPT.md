# 收包清单与第一条执行路径

这是v2增量，不自动安装。压缩包中的历史原ZIP仅作证据，不解压覆盖v2。

1. 用外部`.zip.sha256`比对下载的ZIP。该hash是完整性校验，不是数字签名。
2. 解压后，从本包目录执行`python tools/verify_bundle.py`；必须无missing、unlisted或sha256_mismatch。
3. 本地主Agent只读`HANDOFF_TO_LOCAL_AGENT.md`、`docs/ORDER.md`和`briefs/01_T05.md`即可开始第一增量；完整背景随包提供。

任何清单失败先停止。不要修改MANIFEST让错误“通过”，不要因文件是YAML/界面元数据就跳过。不要把运行日志或Agent修改写回冻结包内；使用获准RUN目录。

工具测试可选，需先把`SMARTCLI_V2_TEST_TMP`设置到已存在的获准RUN。新的真实core检查要求pyte及执行代码许可；在旧baseline上报FAIL正是揭示待修复契约，不是安装失败。

最终交付外部另附`.receipt.json`，记录实际ZIP hash、目录/ZIP完整性结果和数量。收据放在ZIP之外以避免“文件包含自己hash”的循环。metadata与脚本按同样规则验证。
