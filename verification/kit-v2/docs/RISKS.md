# RISKS — 风险登记、停止规则与最大触碰面
这些是审查边界，不是已经发生过的全部事故。A01–A06的证据分级沿用L1；新的设计风险是推断，不能包装成实测。表中kill criteria指**停止该候选方案/本次任务并报告**，不是杀进程或删代码。

| ID | 对象 | 风险 | 触发 | 早期信号 | 处置 | 停止条件 | 最大触碰面 |
|---|---|---|---|---|---|---|---|
|R01|T05|cell坐标再次当字符下标|中文/组合符前缀或0列右界|label与literal不符|按cell取字；保留正文/trim策略|候选仍输出3或mutation不红|3文件：snapshot+vendor+单测|
|R02|T04|整体和分片一起错|仅用whole-feed作oracle|RGB/italic错误但分片一致|独立语义断言+分片对照|独立属性不满足|3文件：screen_model+vendor+单测|
|R03|T04|字符串负载/长CSI污染|正则全局替换、未终止CSI|OSC/DCS被改写或pending增长|状态跟踪、硬cap、明确恢复|控制组退化或无界暂存|同T04；超范围另提案|
|R04|A04|Windows队列无界/假有界|只限制Queue项数或consumer另囤字节|pending超byte cap或RSS趋势异常|计费staging、读上限、背压|靠丢字节保持内存|原型4输出；生产另批≤7文件|
|R05|A04|两reader/两模型owner|为了watcher起第二个pump线程|线程ident变化或字节重复|transport单owner；observer只读快照|任何并发模型写入|生产预算slice最多backend+session及vendor+单测|
|R06|A04|回退interleave修复|重写worker忘掉on_poll|长wait让snapshot再次排队|先锁既有快请求服务测试|移除hook负例抓不住|tui+一个并发测试，独立slice|
|R07|A04|resize冒充动作成功|把resize插入legacy wait|只resize也宣称按键成功|保留延后；未来geometry epoch另设计|resize-only假成功|tui+一个测试，不扩公共API|
|R08|A06|慢回包占owner|同步sendall、非读peer|每回复可占至60s|单独有界回包路径及配额|宣称低延迟但仍阻塞owner|≤3文件：tui+两测试；无新框架|
|R09|T03|短写重发/丢尾/忙等|EAGAIN、EINTR、partial cancel|sink hash/len不同，offset倒退|只写后缀、deadline、明确partial|假成功或无限attempt|最小3；receipt跨session≤5|
|R10|A04|全双工互锁|owner等待写但child先等排输出|deadline反复到期无进度|有界read/write轮转，不递归用户动作|把timeout当成功或新增无界线程|后续生产≤7文件，须拆slice|
|R11|A04|ConPTY关闭/旧reader越代|满buffer、native read未退出、对象复用|旧线程进入新queue或关闭不明|generation绑定、EOF状态、有限收尾|kill全局进程或假称已退出|backend+vendor+专用test，另批E4|
|R12|Protocol|ACK/verified虚构|见prompt/hash变就升级状态|无action/generation或verifier|三事实轴；unknown保留|written直接变业务verified|原型models；公开接线另批≤5文件|
|R13|Packaging|scripts映射被改坏|重命名tui/mcp模块或console entry|source绿wheel导入失败|保持映射；发行矩阵独立门|未经批准破坏旧入口|本轮0个配置文件；发行任务另授权|
|R14|Vendor|sync删除他人修改|直接运行refresh/rmtree|vendor存在非基线变化|只拷允许孪生并跑--check|覆盖独立修改/越过hook|每修复恰好1孪生；不改sync工具|
|R15|Delivery|清单与最终ZIP不一致|manifest后再改yaml/页面|元数据sha不匹配|冻结→manifest→最终ZIP逐项验证|任一缺失/额外/hash差异|仅交付包；不重签未提供的wca包|
|R16|Evidence|SKIP/模型测试冒充产品实测|依赖缺失或故障注入|报告说全通过但NOT_RUN被省|total/pass/skip、环境/注入双标|丢首次失败/假E4|报告/测试；禁止改expected弱化|
|R17|A05|连接和作业配额遗漏|只加ingress cap|readers/jobs仍无界|独立reader/jobs配额+小容量负例|新队列无bound及失效测试|tui+一个或两个测试≤3文件|
|R18|Scope|计划再次膨胀|顺手新引擎/actor/视频平台|变更超allowlist、没有旧失败|按两版won't-do；scope_guard|没有可证收益或超批准面|新增实验最多4个RUN输出，不改生产|

## 每个增量的硬边界
T05/T04各3个文件，分别一份canonical、一份vendor、一份新测试；不把共用模块重命名加进来。T03最小3，涉及receipt跨session最高5，改动理由必须明确。A04-P只在RUN产生4个文件，repo变更为零。A04后续接线最多backend/session/tui +两个core孪生 +两测试=7文件，这个上限不是本轮授权；优先再拆成更小切片。

A05/A06各按tui与独立测试切开，新增线程/队列/observer必须同增量给出上界、取消/关闭策略与失效测试。不新建模块以绕过“文件数量上限”；同样不把一个文件塞成巨大平台来规避控制。任何新重大依赖、默认引擎、公共API破坏或配置变动，都需要另批。

## 检查方法
每个任务开始前捕获文件指纹，结束比较**任务起点**而非一律git HEAD（前一任务可能尚未commit）。
```powershell
& $Python -B "$Kit/tools/scope_guard.py" capture --repo $Repo --out "$Run/T05/before.json"
# 只执行brief允许的修改
& $Python -B "$Kit/tools/scope_guard.py" check --repo $Repo --baseline "$Run/T05/before.json" --brief T05
```
守卫不覆盖repo外/ignored文件，不是sandbox；外部权限仍须人工和已有hook执行。若HEAD变化/未知writer进入，暂停并交接，不自动stash/reset。

## 清单异常处理
web-chat-archive事件只记为用户报告，未接到原ZIP。不能因为只是openai.yaml就忽略验证，更不能给未知内容重算hash后“修复信任”。本包先验证目录，再验证最终ZIP全部列入清单的文件，包含元数据；外部.sha256固定最终ZIP。该校验不提供数字签名身份认证。
