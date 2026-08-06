# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Added
- Makefile `compile-check` target (F365): CI↔Makefile parity gap补全 — ci.yml quality job含 `python -m compileall main.py config.py adapters/ api/ models/ storage/ -q` 编译门控步骤, Makefile `make check` 链此前缺此步骤(CI编译错误本地make check全绿假象); 新增 compile-check target 插入 check 链 lint 前(.PHONY补登), 本地 `make check` 即覆盖CI编译门控; compileall 是Python内置字节码编译器(语法错误/缩进错误零编译期校验的Python里最接近"编译"的步骤); make check 全链复验绿(编译+十四守卫+ruff+pytest 232绿)
- `scripts/check-template-render.sh` (F347): F295模板渲染守卫扩源deploy.sh回退探测目录 — Pi默认仓库路径同名多源补全: F295原对账 Makefile双sed模式↔模板三字面量(unit WorkingDirectory/EnvironmentFile目录段/logrotate日志目录)+渲染逃逸扫描, deploy.sh REPO_DIR回退探测目录(`elif [ -d /home/tl/tianlian-edge-gateway-v3 ]`, 脚本在仓库外执行的引导场景Pi生产路径探测+status/rollback精确进程匹配基准)编码同一事实"Pi仓库在此路径"是第六处字面量盲区; 历史真实漂移事故(deploy.sh头部注释留档): 旧值 /home/tl/tianlian-v3-edge-gateway 词序写反在Pi上不存在→cd失败set -e第2步即死; 漂移后果(最恶形态=静默): 模板/sed侧整体改名(F295全绿)而回退目录漏同步→引导场景探测旧路径永不命中, 部署静默中止, 且REPO_DIR错误使status/rollback进程匹配基准脱钩; → 补断言5: 回退目录提取(`elif [ -d /home/...` 行内字面量)==sed模式 + 提取非空活性 + deploy.sh缺输入即FAIL(F212不放行), 成功消息标注F347; 接线复用F295既有(make template-render-check+CI, 守卫计数不变十四枚); 变异两档实测(deploy.sh:61回退字面量改为历史事故原值/home/tl/tianlian-v3-edge-gateway词序漂移档精确拦exit 1 / mv走deploy.sh缺输入拦exit 1, cp备份还原diff零残留基线exit 0); make check全绿(十四守卫); pytest 232绿
- `scripts/check-log-paths.sh` (F341): F261日志路径守卫全域扩源——声明源外字面量写读点扫描; F261原对账锚定三声明源(logrotate轮转目标/deploy.sh nohup重定向/watchdog LOG_FILE声明), 代码内绕过声明的硬编码字面量是盲区(实证存量两处): ① watchdog.sh systemd退位消息直写`>> $REPO_DIR/gateway.log`(绕过下方LOG_FILE变量, 声明改名后此处仍写旧名) ② deploy.sh status/logs子命令tail读引用×2(声明改名后永显"(无日志)"运维误判日志丢失); 漂移后果(最恶形态=静默): 三声明源同步改名(F261全绿)而字面量漏同步→watchdog继续写旧文件名幻影日志(missingok轮转不到→无限增长写满Pi磁盘, 与F261原动机同果); 扫描域: deploy.sh+scripts/*.sh(排除check-*守卫脚本——其regex/注释含.log字面量非行为写读; Makefile不入域——.tianlian-gateway.logrotate.rendered中间产物名含".log"子串但非应用日志), 注释行剥除(文档提及非行为); 断言: 全部字面量basename==轮转目标+提取非空活性断言(F212不放行); 接线复用F261既有(make log-paths-check+CI, 守卫计数不变十四枚); 变异两档实测(watchdog.sh:26写侧字面量改名watchdog-retire.log精确拦exit 1——旧版守卫此档必放行即扩源动机实证 / deploy.sh:197 tail读引用改名gateway.old.log精确拦exit 1, cp备份还原diff零残留基线exit 0); make check全绿(十四守卫); pytest 232绿
- `scripts/check-env-keys.sh` (F332): env键守卫读取侧扩源 config.py单文件锚定→全仓Python扫描 — F255原读取侧只锚定config.py一个文件, 新模块绕过config.py直读os.environ/os.getenv成为对账盲区(读取侧单源化=扩源前同型漂移通道, F320扩源形态同源); 三形态全覆盖: os.getenv("K")/os.environ.get("K")/os.environ["K"]; 扫描排除隐藏目录(venv系, 实测.venv-build含pip/site-packages共1534个py文件会误吸122键——venv系库代码读环境变量不是部署契约)+tests/(测试代码不消费生产.env)+__pycache__; 同源修复提取器键名字符集[A-Z_]→[A-Z0-9_](含数字键如OAUTH2_*原被静默漏提, 双侧提取模式对称放宽); 断言语义不变: 读取侧↔.env.example双向相等, 缺输入/提取空/不等均exit 1(F212不放行); 接线复用F255既有(make env-keys-check+CI, 守卫计数不变十四枚); 变异两档实测(api/server.py注入config.py外os.getenv探针键精确拦exit 1——旧版守卫此档必放行即扩源动机实证 / 同位改os.environ.get形态精确拦exit 1, cp备份还原diff零残留基线exit 0 20键双向一致); make check全绿(十四守卫); pytest 232绿
- `scripts/check-env-file.sh` (F326): .env凭据语义四源对账守卫(部署守卫族第十四枚) — .env凭据文件身份散布多源此前零断言(F295只覆盖EnvironmentFile目录段↔sed渲染模式一致性): ① unit EnvironmentFile的"-"前缀形态(静默容忍缺失) ② unit侧basename ③ docker-compose env_file basename(容器侧凭据文件) ④ .gitignore精确".env"保护条目; 漂移后果(最恶形态=静默): EnvironmentFile单侧加"-"前缀→缺文件被systemd静默容忍CLOUD_TOKEN等全键吃默认值, 云端认证失败排障无从下手 / unit侧basename改走(如env.production)而compose侧不同步→容器/宿主两模式读不同凭据文件, 排障结论互相矛盾 / basename改走后.gitignore仍只保护".env"→新文件名的真实凭据被误commit泄密 → 脚本断言: 无"-"前缀(静默容忍=禁) + basename==.env + compose basename==unit侧 + .gitignore含精确".env"行, 缺输入/提取空/不等均exit 1(F212不放行); unit模板路径取自deploy.sh UNIT_FILE默认值(F236已守三源同名)不硬编码; 接入 make check(env-file-check target, check链委托单一源, .PHONY补登) + CI check job; 变异三档实测(unit basename .env→env.production双分支并报精确拦exit 1 / compose env_file单侧改名精确拦exit 1 / "-"前缀注入静默容忍分支精确拦exit 1, cp备份还原diff零残留基线exit 0); make check全绿(十四守卫); pytest 232绿; README门控章节十三项→十四项
- `scripts/check-api-port.sh` (F320): API端口多源一致性守卫扩源五→六 — F249原对账 config.py↔deploy.sh↔compose↔EXPOSE↔HEALTHCHECK 五源, scripts/watchdog.sh `PORT="${PORT:-8080}"`(cron存活探测HEALTH_URL与ss端口判定共用此变量, 直跑模式下进程生死的唯一裁判)是端口侧盲区(F280补的是路径侧, 端口侧watchdog源无人对账); 漂移后果(最恶形态=静默重启风暴): API端口声明变更后F249四源同步而watchdog漏同步→cron存活探测永打旧端口→健康进程被反复判死kill循环重启, 且deploy.sh健康检查亮着=两侧探测结论互相矛盾, 边缘设备最难排障形态 → 补watchdog.sh缺输入断言+PORT默认值提取+==声明侧断言, 成功消息五源→六源; 变异两档实测(watchdog PORT 8080→8081精确拦exit 1 / mv走watchdog.sh缺输入拦exit 1, cp备份还原基线exit 0零残留); make check全绿(十三守卫); pytest 232绿
- `scripts/check-start-interpreter.sh` (F314): 启动解释器多源对账守卫(部署守卫族第十三枚) — 生产启动解释器字面量散布四源零断言: ① deploy.sh `PYTHON="python3"` 声明(nohup直启分支) ② scripts/watchdog.sh `nohup python3` 硬编码字面量(systemd退位后唯一复活源) ③ systemd/tianlian-gateway.service `ExecStart=/usr/bin/python3` ④ Dockerfile `CMD ["python3", ...]`; F287(python-version-check)只覆盖"最低版本数字"七声明源, 启动命令行解释器token是盲区; 漂移后果(最恶形态=静默): deploy.sh单侧换解释器(版本化二进制/venv路径)→watchdog/systemd/Docker未同步→watchdog复活进程静默用旧解释器, 新语法/新标准库运行时才崩(F287版本声明全绿但实际进程跑错解释器) / systemd ExecStart换版本不同步→重启后行为与deploy直启分叉, 排障两模式复现不一致; Makefile run目标走 $(VENV)/bin/python 是dev venv语义与生产裸解释器刻意不同, 豁免入列但断言提取非空; → 脚本断言四生产源归一化(basename去目录前缀)后精确相等 + 各源提取≥1(活性断言防豁免吞断言), 缺输入/提取空/漂移均exit 1(F212不放行); 接入 `make check`(start-interpreter-check target, check链委托单一源, .PHONY补登pid-file-check+start-interpreter-check——F308轮漏登欠账同源清) + CI check job; 变异实测(watchdog nohup字面量python3→python改名档精确拦exit 1, cp备份还原基线exit 0零残留); make check全绿(十三守卫); pytest 232绿; README门控章节十二项→十三项
- `scripts/check-pid-file.sh` (F308): pid文件写读对账守卫(部署守卫族第十二枚) — 直跑模式(nohup)下进程pid靠仓库根 .pid 文件交接, 四处字面量声明零断言: 写侧① deploy.sh start_gateway `echo "$NEW_PID" > .pid` ↔ 读侧②③ deploy.sh step6停旧 `[ -f .pid ]`+`cat .pid`(pgrep未中时兜底) ↔ 读写侧④ watchdog.sh `PID_FILE="$REPO_DIR/.pid"`(取pid读+重启后写回); 漂移后果(最恶形态=静默): watchdog侧PID_FILE改名→重启写回的文件deploy.sh停旧永不读→pgrep同时失配(cmdline漂移)时旧进程漏kill→双启撞端口/重启风暴(F217/F230同族后果) / deploy.sh写侧改名→watchdog读旧名落空回退pgrep, pid交接链路静默失效, 排障只见双启现象不见根因 / 目录段漂移→两基准脱钩同效; → 脚本断言四提取点精确相等 + watchdog目录段==仓库根(与deploy.sh相对路径同基准) + 活性断言(deploy写点≥1/watchdog读点≥1/写点≥1, 防豁免吞断言), 缺输入/提取空/漂移均exit 1(F212不放行); 接入 `make check`(pid-file-check target, check链委托单一源) + CI check job; 变异四档实测全中(deploy写侧改名精确拦exit 1 / watchdog PID_FILE改名精确拦exit 1 / watchdog目录段漂移run/.pid精确拦exit 1——**首档即撞守卫自身目录段判定逻辑盲区(case前缀斜杠匹配对相对路径恒不命中), 同源修复为含斜杠即漂移** / mv走watchdog.sh缺输入拦exit 1, cp备份还原基线exit 0零残留); make check全绿(十二守卫); pytest 232绿; README门控章节十一项→十二项
- `scripts/check-backup-restore.sh` (F301): 备份写读对账守卫(部署守卫族第十一枚) — deploy.sh 迁移前备份写模式与回滚/保留读glob分四处字面量维护零断言: 写侧①② `BAK="data/backups/gateway.db.$TS[-$SUFFIX].bak"`(主备份+后缀变体) ↔ 读侧③ rollback `ls -1t data/backups/gateway.db.*.bak` 选最新 ↔ 读侧④ retention同glob `tail -n +6` 清理, 另 DB_FILE="data/gateway.db" deploy.sh内双处声明(rollback分支+部署分支)↔config.py db_path字段默认值(F267声明侧权威源)零对账; 漂移后果(最恶形态=静默): 写侧改名(如.bak→.backup)→读glob永远匹配不到任何备份→"无备份可用"在凌晨3点回滚现场才暴露 / retention glob漂移→旧备份永不清理占满边缘设备磁盘 / DB_FILE单侧漂移→rollback恢复目标≠真实DB位置(恢复成功假象+数据仍在旧处); F267已覆盖config.py↔Dockerfile↔compose↔备份basename, 写模式形态↔读glob形态互配+DB_FILE双处同源是盲区 → 脚本断言: 写侧每模式(前缀+$变量+后缀)推导期望glob==读glob(唯一) + 读glob≥2消费点(rollback+retention)全同 + DB_FILE≥2处全同且==config.py db_path默认 + 读glob目录==dirname(DB_FILE)/backups, 缺输入/提取空/漂移均exit 1(F212不放行); 接入 `make check`(backup-restore-check target, check链委托单一源) + CI check job; 接手轮变异四档实测全中(写侧后缀.bak→.backup精确拦exit 1 / 读glob单侧后缀延伸.bak→.bak2精确拦exit 1——**首跑撞守卫自身提取盲区: 提取regex锚定\*\.bak把.bak2静默截断为.bak漏检, 同源修复为提取整token再滤*号** / DB_FILE单侧漂移多处分叉拦exit 1 / mv走deploy.sh缺输入拦exit 1, cp备份还原基线exit 0零残留); make check全绿(十一守卫); pytest 232绿; README门控章节十项→十一项
- `scripts/check-template-render.sh` (F295): 部署模板渲染路径一致性守卫(部署守卫族第十枚) — make systemd-install 用 sed 把 unit/logrotate 模板中的Pi默认硬编码路径渲染为 CURDIR(F211), sed模式(Makefile两行)↔模板路径字面量(unit WorkingDirectory + EnvironmentFile目录段 + logrotate日志路径目录段三处)是同名双源零断言: 任一侧单独改动→sed静默no-op(不报错!)→渲染产物仍带模板默认路径→非Pi主机 systemd WorkingDirectory不存在即启动失败/读错.env, logrotate指向不存在日志(missingok静默跳过→日志无人轮转膨胀写满Pi磁盘, 边缘设备最恶故障形态) → 脚本断言 Makefile双sed模式相等(双源单语义) + 模板三字面量↔模式精确一致(含unit内 WorkingDirectory==dirname(EnvironmentFile) 同目录语义) + 渲染逃逸全扫描(模板内任何/home/*绝对路径必须以模式开头) + 每模板模式命中数≥1, 缺输入/提取空/漂移均exit 1(F212不放行); 接入 `make check`(template-render-check target, check链委托单一源) + CI check job; 变异四档实测(unit WorkingDirectory漂移精确拦exit 1 / Makefile sed模式单侧漂移→双源+三字面量+逃逸+零命中多源并报exit 1 / logrotate路径逃逸+零命中拦exit 1 / mv走unit模板缺输入拦exit 1, cp备份还原基线exit 0零残留); make check全绿(十守卫); pytest 232绿; README门控章节九项→十项
- `scripts/check-python-version.sh` (F287): Python 最低版本多源一致性守卫 — 运行时最低版本 3.10(Pi生产)散布七类声明源零断言: ① deploy.sh `[ "$PY_MINOR" -lt 10 ]` 执行预检(权威) ② deploy.sh "需要 Python 3.10+"/"< 3.10" 提示(同文件双声明F267族) ③ ci.yml python-version ④ Dockerfile FROM python:3.10-slim ⑤ pyproject.toml ruff target-version ⑥ DEPLOYMENT.md "低于 3.10 告警" ⑦ README.md "Python 3.10+"/"py3NN" 转述; 漂移后果: 任一侧单独bump(如CI/Dockerfile升3.12)→新解释器放行3.11+语法/标准库(pyproject已为此显式ignore UP017)在Pi 3.10运行时崩溃, README转述漂移误导部署者装错解释器; → 脚本断言七源minor全等, 缺输入/提取空/不一致均exit 1(F212不放行); 接入 `make check`(python-version-check target, check链委托单一源) + CI check job; **首跑即撞真实存量漂移(对账守卫首跑撞存量第四验F252/F277/F285): README "ruff target py313" vs pyproject实际py310** → 同源修复README(py313→py310)+pyproject注释(py313现代化→py310基线); 顺手补Makefile .PHONY漏登health-probes-check(F280轮欠账); 变异三档实测(ci.yml bump 3.11/Dockerfile bump 3.12/mv走DEPLOYMENT.md缺输入均精确拦exit 1, sed反向还原基线exit 0零残留); make check全绿(九守卫); pytest 232绿; README门控章节八项→九项
- `scripts/check-health-probes.sh` (F280): 健康探测路径多源一致性守卫 — 存活探测路径 /health 的探测源三处独立维护零断言: ① deploy.sh curl http://localhost:$PORT/health(部署成功判定/status子命令) ② watchdog.sh HEALTH_URL(cron存活探测) ③ Dockerfile HEALTHCHECK CMD curl, 声明侧 api/server.py @app.get("/health"); F243只覆盖deploy.sh↔server.py单向, watchdog/Dockerfile探测路径是盲区(F249只覆盖端口侧); 漂移后果: 服务端路由单独改名→watchdog curl 404(-f判失败)→健康进程被判卡死→kill循环反复重启 / Docker HEALTHCHECK失败→容器判unhealthy→restart:unless-stopped重启循环 / deploy.sh健康判定循环永不亮; → 脚本断言三探测源路径集合各自⊆server.py声明路由集 + watchdog↔Dockerfile存活探测路径相等(同一存活语义必须单一源F259), 缺输入/提取空/不一致均exit 1(F212不放行); 接入 `make check`(health-probes-check target, check链委托单一源) + CI check job; 变异三档实测(server.py路由改名/healthz→三源并报精确拦exit 1 / watchdog路径改名→子集+双源漂移并报精确拦exit 1 / mv走Dockerfile缺输入拦exit 1, sed反向还原后基线exit 0零残留); make check全绿(八守卫); pytest 232绿; 顺手清README门控章节陈旧描述(五项→八项)
- `scripts/check-entry-file.sh` (F273): 入口文件多源一致性守卫 — 入口文件名 main.py 分源散布于六类启动/探测声明: ① systemd unit ExecStart ② Dockerfile CMD ③ Makefile run 目标 ④ watchdog.sh nohup 启动 ⑤ deploy.sh REPO_DIR 探测 ⑥ deploy.sh nohup 启动, 另对账 pgrep -f "$REPO_DIR/<入口>" 进程匹配模式×5(deploy.sh×4 + watchdog×1)文件名唯一且==入口声明 + 入口文件磁盘实存; 漂移后果: 任一侧单独改入口文件名→pgrep 模式未同步→杀旧进程永不命中→双启撞端口 / status 误报"未运行"(静默), unit/Dockerfile 未同步→服务重启即失败, 探测未同步→REPO_DIR 探测失败部署中止 → 脚本断言六声明源相等 + pgrep 模式唯一对齐 + 实存, 缺输入/提取空/不等/缺文件均 exit 1(F212不放行); 接入 `make check`(entry-file-check target, check链委托单一源) + CI check job; 变异三档实测(Dockerfile CMD 改名精确拦 exit 1 / deploy.sh 单处 pgrep 模式改名精确拦 exit 1 / mv 走 watchdog.sh 缺输入拦 exit 1, sed 反向还原后基线 exit 0 零残留); 接手轮同源修复: 六处提取补 `|| true`(原缺失输入时 set -e 崩溃 exit 2, 偏离 F267 族惯例的友好提示+exit 1); make check 全绿(七守卫); pytest 232绿
- `scripts/check-data-paths.sh` (F267): 数据持久化路径多源一致性守卫 — SQLite DB路径五源分源维护零断言: ① config.py dataclass字段默认值 `db_path: str = "data/gateway.db"`(声明侧权威源) ② config.py os.getenv("STORAGE_DB_PATH") fallback默认值(同文件第二声明, env未设时行为取决于读取路径) ③ Dockerfile WORKDIR+VOLUME(容器内持久化挂载点) ④ docker-compose.yml 命名卷挂载目标(容器侧路径) ⑤ deploy.sh 迁移前备份glob `data/backups/gateway.db.<ts>.bak`; 漂移后果: ①单独迁路径(如storage/)→容器卷不再覆盖真实DB→容器重建数据静默丢失(边缘设备最恶故障)/①≠②→默认值分叉/⑤basename漂移→备份与回滚glob永远匹配不到真实DB → 脚本断言 ①==②, WORKDIR+dirname(①)==③==④(/app前缀过滤排除localtime系统挂载), dirname(①)==⑤目录前缀, basename(①)==⑤备份basename, 缺输入/提取空/不等均 exit 1(F212不放行); 接入 `make check`(data-paths-check target, check链委托单一源) + CI check job; 变异六档实测(字段默认漂移/getenv默认漂移/VOLUME改名/compose挂载改名/备份basename改名/mv走compose缺输入均精确拦 exit 1, 每档 sed 反向还原后基线 exit 0 零残留); make check 全绿(六守卫); pytest 232绿
- `scripts/check-log-paths.sh` (F261): 日志路径双源漂移守卫 — nohup模式日志写侧 deploy.sh 重定向目标(`nohup ... > gateway.log`)与 scripts/watchdog.sh LOG_FILE, 轮转侧 systemd/logrotate.conf 轮转目标, 两侧独立维护零断言: 任一侧单独改文件名→logrotate 轮转不存在路径(missingok 静默跳过)→真实日志无人轮转→Pi 磁盘被日志写满(静默, 边缘设备最恶故障); 另断言 logrotate 路径目录段 == unit WorkingDirectory 默认值(两段共用 make systemd-install 的 sed 渲染占位符, 目录段漂移→渲染不到→装出的轮转仍指旧路径) → 脚本断言轮转↔deploy↔watchdog basename 三源一致 + 目录段对账, 缺输入(F212不放行)/提取空/不等均 exit 1; unit模板路径取自 deploy.sh UNIT_FILE 默认值(F236已守三源同名)不硬编码; 接入 `make check`(log-paths-check target, check链委托单一源) + CI check job; 变异五档实测(deploy写侧改名/logrotate轮转目标改名/watchdog写侧改名/logrotate目录段漂移/mv走logrotate.conf缺输入均精确拦 exit 1, 每档 sed 反向还原后基线 exit 0 零残留); bash -n + YAML解析 + make -n OK; pytest 232绿; 顺手清 ruff 2债务(test_api.py I001 import排序 + PIE807 lambda→dict, 基线登记在案债务清零, make check 全绿)
- `scripts/check-env-keys.sh` (F255): 环境变量键名双源一致性守卫 — 读取侧 config.py os.getenv 键集合(20键: GATEWAY_*/CLOUD_*/MQTT_*/MODBUS_*/OCPP_*/STORAGE_DB_PATH/LOG_LEVEL, 代码实际读取的权威源) ↔ 模板侧 .env.example 键清单(部署者照抄模板, compose env_file: .env 由部署者从.example复制), 双源同名零断言: 代码新增 os.getenv 键而 .example 未登记→部署者漏配静默吃默认值(如 CLOUD_TOKEN 漏配→云端认证失败排障无从下手)/.example 残留代码已不读取的死键→误导部署者配置无效项 → 脚本提取两侧键集合双向对账(comm 双向差集), 缺输入/提取空/不等均 exit 1(F212不放行); 接入 `make check`(env-keys-check target, check链委托单一源) + CI check job; 变异三档实测(config.py 新增 os.getenv 键精确拦 exit 1 / .env.example 追加死键精确拦 exit 1 / mv走 .env.example 缺输入拦 exit 1, 每档 sed 反向还原后基线 exit 0 且 git diff 零残留); bash -n + YAML解析 + make -n OK; pytest 232绿
- `scripts/check-api-port.sh` (F249): API端口多源一致性守卫 — 声明侧 config.py LocalAPIConfig.port(api/server.py 实际 listen 端口), 探测/发布侧 deploy.sh PORT 默认值/docker-compose ports 映射/Dockerfile EXPOSE/Dockerfile HEALTHCHECK 探测端口, 多源同名零断言: 任一侧单独改端口→deploy.sh 健康探测旧端口永不亮(健康服务被报部署失败)/Docker HEALTHCHECK 探测旧端口=容器反复判不健康 → 脚本以声明侧默认值对账四源, 缺输入/提取空/不等均 exit 1(F212不放行); 接入 `make check`(api-port-check target, check链委托单一源) + CI check job; 变异四档实测(config.py声明侧改名精确拦 exit 1 / deploy.sh探测侧改名精确拦 exit 1 / Dockerfile HEALTHCHECK 改名精确拦 exit 1 / mv走 docker-compose.yml 缺输入拦 exit 1, 每档 sed 反向还原后基线 exit 0); bash -n + YAML解析 + make -n OK; pytest 232绿
- `scripts/check-deploy-endpoints.sh` (F243): 部署探测端点一致性守卫 — deploy.sh 部署成功判定(HEALTH_OK循环)+status子命令探测 `http://localhost:$PORT/health` 与 `/api/v1/status`, 路由声明在 api/server.py(@app.get装饰器), 两侧独立维护零断言: 服务端路由单独改名→部署成功判定循环永远不亮(健康服务被报部署失败)/status"不可达"; 探测侧单独改错→同果 → 脚本提取deploy.sh探测路径集合(排除$(hostname)展示行), 断言全部∈server.py声明路由集合, 任一侧缺输入/提取空/不一致均exit 1(F212不放行); 接入 `make check`(deploy-endpoints-check target, check链委托单一源) + CI check job; 变异三档实测(服务端/health→/healthz精确拦exit 1 / 探测侧/health→/healthcheck精确拦exit 1 / mv走server.py缺输入拦exit 1, 每档sed反向还原后基线exit 0); bash -n + YAML解析 + make -n OK; pytest 232绿

### Added
- `scripts/check-deploy-names.sh` (F236): 部署同名源一致性守卫 — SYSTEMD_MODE探测(F217/F230退位守卫)依赖 deploy.sh/watchdog.sh 的 UNIT_FILE 默认值与 Makefile systemd-install 实际安装路径**精确同名**, 三处任一单独改名→unit已装但探测失配→退位守卫整体失效(kill+nohup撞systemd Restart=always重启风暴); logrotate同理(Makefile安装名 vs deploy.sh部署尾提示探测名漂移→提示误报/漏报) → 脚本对账unit三源+logrotate双源, 不一致即exit 1, 并断言unit模板 systemd/<basename> 存在; 接入 `make check`(deploy-names-check target) + CI check job; 变异两档实测(watchdog UNIT_FILE改名→三源漂移精确拦截exit 1 / Makefile logrotate安装名改名→双源漂移精确拦截exit 1, 基线exit 0); pytest 232绿

### Fixed
- `scripts/watchdog.sh` (F230): systemd模式退位守卫 — F217同族漏网点: unit已装时systemd接管进程生死(Restart=always), watchdog仍按cron/loop定时kill+nohup重启: ①杀卡死进程后unit 5秒内复活, 与nohup第二实例撞端口(重启风暴); ②.pid被改写指向nohup实例, systemd实例失联 → 与deploy.sh一致的SYSTEMD_MODE探测(unit文件存在, `TIANLIAN_UNIT_FILE`可覆盖测试钩子), 命中即记日志+exit 0整体退位, 绝不启动第二进程, 恢复交给Restart=always; 变异三档实测(unit存在→exit 0+退位日志+未进flock/unit不存在+健康→过守卫正常exit 0零退位日志/bash -n通过); README+DEPLOYMENT.md同步说明

### Fixed
- `deploy.sh` rollback (F223): 迁移盲区守卫 — rollback只revert代码, 若回滚范围内含 db_migration.py 变更, 数据库schema已被新版本前移, revert后直接 `bash deploy.sh` 重部署会让旧代码跑在新schema上(“no such column”崩/数据错乱)且全程零提示 → revert前探测范围内迁移commit(`git log RANGE -- db_migration.py`), 命中即醒目警告+引导 `restore-db` 恢复迁移前备份并列出可用备份; 变异三档实测(范围含迁移commit→精确警告含commit清单/范围无迁移commit→零警告行为不变/ bash -n 语法通过); pytest 232绿

### Fixed
- `deploy.sh` (F217): 双模式冲突守卫 — unit已安装(make systemd-install)时, 主流程仍pgrep+kill停进程+nohup启新实例: `Restart=always`在kill后5秒内复活systemd进程, 与nohup第二实例撞端口(一者无限重启风暴/新代码未生效假部署); `restore-db`同型(kill后复活进程立即写回刚恢复的库) → 新增SYSTEMD_MODE探测(unit文件存在即systemd模式), 步骤6/7与restore-db停启全部委托`systemctl stop/start`(start后取MainPID接健康检查轮询), systemd模式下不写.pid/不nohup/日志提示切journalctl; stop失败即中止(exit 1, 不碰库); 变异三档实测(systemd模式stop+start调用链精确/直跑模式零systemctl调用行为不变/stop失败exit 1库不动); systemd/README.md新增自动探测章节

### Fixed
- `Makefile` systemd-install (F211): 路径漂移守卫 — unit/logrotate 模板硬编码 `/home/tl/tianlian-edge-gateway-v3`(Pi默认路径), 旧安装裸 `sudo cp`, 仓库位于其他目录时(deploy.sh REPO_DIR 自动探测支持任意含 main.py 目录)装出的 unit WorkingDirectory/EnvironmentFile 与 logrotate 路径指向不存在目录 → 服务起不来/日志轮转静默失效(missingok) → 安装时 sed 渲染为 $(CURDIR)；三档实测(非默认路径替换3处精确/默认路径 no-op diff零/ make -n CURDIR展开正确)；deploy.sh 两处提示+systemd/README.md 手动步骤同步收敛到 `make systemd-install`(F195单一源模式)

### Changed
- CI (ci.yml): 两 job 补 `timeout-minutes`（quality=15 / docker=20）— F193模式例行体检撞出：此前均无超时，挂死最多吃满 GitHub 默认 6h runner；YAML 解析+结构断言校验（timeout/concurrency/coverage产物 if:always 均实测确认）。本地无 act 环境，结构化校验替代

### Fixed
- `scripts/watchdog.sh` (F205): cron单次模式补 flock 互斥 — 恢复窗口(~75s: 3轮启动健康等待+RESTART_DELAY)可跨cron触发周期，此前两实例并发恢复会双启gateway、后启者覆盖`.pid`致先启进程成孤儿(占端口但pid失联)、后来者端口冲突反复失败 → `exec 9>lock + flock -n`拿不到锁即跳过本轮；变异实测双向(有锁: 并发实例13ms exit 0零日志贡献 / 无锁对照: 两实例同时进恢复, 探针有效)
- `.gitignore`: 补运行时产物 `.pid`/`.watchdog.lock`/`gateway.log`(deploy.sh/watchdog.sh在部署目录生成, F10同型噪音)
- `deploy.sh` (v8): 步骤5迁移失败黑洞 — 旧写法 `2>/dev/null || echo` 吞掉真失败（`db_migration.py` 幂等成功恒 exit 0，真失败 exit 1），带病继续会杀旧服务起新代码，旧schema库运行时即 "no such column" 崩 → 迁移失败即中止部署（此时旧服务未停，零影响）；实测坏库场景确认中止（exit 1）
- `deploy.sh` (v8): 备份同秒碰撞覆盖 — 时间戳备份名同秒重跑会静默覆盖上一份备份（实测复现：好备份被坏库内容覆盖）→ 目标已存在时追加 `-1/-2` 后缀，绝不覆盖旧备份

### Added
- `deploy.sh` (v8): 迁移前自动备份 `data/gateway.db` → `data/backups/gateway.db.<时间戳>.bak`（仅保留最近5份，轮转实测确认），备份失败即中止部署；新子命令 `restore-db [备份文件]`：停网关→恢复备份（缺省最新一份），实测旧schema库迁移6项+坏库中止+同秒双备份+恢复闭环全过；`make deploy-restore-db [BAK=...]` 委托单一源

### Fixed
- `deploy.sh` (v7): 步骤5迁移脚本真缺口 — 旧 `migrate_db.py` 只补 `cloud_synced`/`priority` 两列，旧schema库缺 `cached_at`/`retry_count`/`synced` 时迁移后 schema 仍不全，运行时查询即 "no such column" 崩；实测对比（旧schema临时库两脚本各跑+幂等复跑）确认 `db_migration.py` 全量补齐且幂等 → 切换 `migrate_db.py`→`db_migration.py`，旧脚本退役移除
- systemd 单元双源漂移修复：移除根目录旧版 `tianlian-edge-gateway.service`（无安全加固、Restart=on-failure+StartLimitBurst=3 崩溃3次后不再拉起、日志双写），唯一源为 `systemd/tianlian-gateway.service`；README 原安装指引指向旧版（误装会导致网关崩溃后永久下线）→ 改为方式五指向 systemd/ 版；DEPLOYMENT.md 说明同步
- `deploy.sh` (v6) + `Makefile deploy-rollback`: 回滚 stash 黑洞（F172遗留实测发现）— v5 先 stash 脏改动再 revert，但失败路径声称"恢复现场"却不 pop stash（用户未提交改动看似丢失），成功路径也不提 stash 去向 → 记录 stash 计数，失败自动 `git stash pop` 真正恢复现场，成功提示 `stash@{0}`；失败提示补 merge commit 场景（范围含 merge 时 revert 需 `-m`）与手动处理指引；Makefile deploy-rollback 从重复实现改为委托 `deploy.sh rollback`（单一源，防护一致）。临时仓库 5 用例实测：干净线性/脏树保留stash/merge+脏改动失败pop恢复/Makefile委托/无效commit与REV=HEAD防护 全过
- `deploy.sh` (v5) + `Makefile deploy-rollback`: 回滚语义bug — `git revert $REV` 只撤销单个commit，与"回滚到REV"语义不符（落后N个commit时只撤1个，其余N-1个坏提交仍在）→ 改 `git revert ${REV}..HEAD` 撤销目标好版本之后全部提交，工作区即REV状态；新增 无效commit校验/REV即HEAD短路/revert冲突自动abort 三重防护

### Added
- CI: 新增 `docker` job（与 quality 并行）— buildx 构建镜像(GHA缓存, 不推送) + 容器内无环境变量 `import main` 冒烟，Dockerfile/依赖损坏在 push 阶段即被拦截
- `.dockerignore`: 补 tests/docs/.github/systemd/*.log/coverage.xml → 运行时镜像瘦身
- `DEPLOYMENT.md`: 部署前门禁说明同步 CI docker 构建门

### Fixed
- `deploy.sh` (v4): `status` 子命令 `pgrep -f 'main.py'` 匹配过宽（会命中任意目录的 main.py）→ 改用 `$REPO_DIR/main.py` 精确匹配，REPO_DIR 探测提前到子命令之前
- `deploy.sh` (v4): 启动用相对路径 `main.py` 导致 cmdline 不含路径，step6/watchdog 的精确 pgrep 永不命中（杀旧全靠 .pid/fuser 兑底）→ 改绝对路径启动
- `scripts/watchdog.sh`: 同步改绝对路径启动，与 get_pid 匹配模式对齐

### Added
- `deploy.sh` (v4): Python 版本预检（<3.10 告警不阻断，兼容老环境）

### Fixed
- `systemd/tianlian-gateway.service`: 移除 `ProtectHome=read-only`（SQLite DB 在 /home 下，只读会导致写库全面失败）
- `scripts/watchdog.sh`: REPO_DIR 误指向 scripts/ → pgrep 永不匹配真实网关进程，看门狗形同虚设；改为仓库根

### Added
- `DEPLOYMENT.md`: 部署运行手册（deploy.sh/systemd/Docker 三方式 + watchdog + 踩坑记录 + 已知问题）


### Added
- `docs/API_REFERENCE.md`: 完整 API 参考手册（8 端点，含请求/响应示例 + curl 快速验证）
- `docs/DEVELOPMENT.md`: 开发贡献指南（环境搭建 / 项目结构 / 核心概念 / 扩展指南 / 测试规范）
- README: 新增「更多文档」导航段 + 目录结构补 docs/
- deploy.sh: `rollback` 子命令（`bash deploy.sh rollback <commit-hash>` 安全回滚）
- deploy.sh: `status` 子命令（快速查看 PID/健康检查/状态API/日志尾部）
- Dockerfile: `$BUILDPLATFORM`/`TARGETPLATFORM` 多架构支持（ARM64 Pi + AMD64 开发机）
- Makefile: `docker-build`/`docker-up`/`docker-down`/`docker-logs`/`docker-shell` Docker 快捷命令
- Makefile: `deploy-rollback` 目标（`make deploy-rollback REV=<hash>`）

### Changed
- Dockerfile: `FROM --platform=$BUILDPLATFORM` 支持多架构构建（buildx 多平台镜像）
- Makefile: `.PHONY` 补全 Docker + rollback 目标

### Added (历史)
- `Dockerfile`: 多阶段构建（python:3.10-slim + 非 root 运行 + HEALTHCHECK 健康检查 + 数据卷持久化）
- `docker-compose.yml`: 一键容器化部署（restart:unless-stopped + 日志轮转 + 时区同步 + 持久化卷）
- `.dockerignore`: 排除 .venv/.git/data 等，优化构建上下文
- `scripts/watchdog.sh`: 看门狗脚本（健康检查 + 自动重启 + 连续3次失败告警；支持 crontab 单次模式和 --loop 常驻模式）
- `systemd/tianlian-gateway.service`: systemd unit（Restart=always + RestartSec=5 + 安全加固 NoNewPrivileges/ProtectSystem/PrivateTmp）
- `systemd/README.md`: systemd 安装/管理/从 deploy.sh 迁移指南
- `systemd/logrotate.conf`: gateway.log 日志轮转（daily/rotate7/compress/copytruncate）
- deploy.sh: systemd 检测+迁移建议 / 日志轮转提示
- Makefile: systemd-install/start/stop/restart/status/logs 快捷命令
- `tianlian-edge-gateway.service`（旧记录）: systemd 单元初版
- `.env.example`: 全量环境变量模板，18 个 key 与 `config.py` `os.getenv` 精确对齐
- `Makefile`: venv/install/run/test/lint/check/clean/deploy 开发快捷命令
- README.md：架构、环境变量、本地 API、测试与部署说明（自驱文档轮补全，此前仓库无 README）
- 本 CHANGELOG
- README 补充故障排查（troubleshooting）段和配置文件说明
- README 补全环境变量表（STORAGE_DB_PATH/LOG_LEVEL/MQTT_CLIENT_ID）和 .env 文件段

## 2026-08-01

### Changed
- `95cb038` style(lint): 修复 W292（EOF 缺换行×9）+ E501（行过长×6）
- `b3f8f22` fix(deploy): deploy.sh v3 — 端口释放等待循环 + 启动重试 + 健康轮询（解决旧进程杀后端口未释放致 bind 失败）
- `8ef586c` fix(deploy): .env 从未加载到环境变量——deploy.sh 启动前 source .env；kill -9 兜底确保端口释放
- `65faebd` fix(py310-compat): StrEnum→(str, Enum) 回退（Pi Python 3.10 无 StrEnum）
- `3da23cb` fix(py310-compat): datetime.UTC→timezone.utc（Pi 3.10 兼容）；deploy.sh 语法修复；pyproject target py310 + ignore UP017
- `192192a` fix(deploy): 修复 deploy.sh 两处语法损坏（REMOTE= 赋值被截断）

## 2026-07-31

### Changed
- `0f1c94f` lint(F841/UP035/UP042): 清零 3 类 ruff 债务（F841×4 unused-var 删除 / UP035×3 typing→collections.abc / UP042×11 str+Enum→StrEnum）；pyproject.toml ignore 列表同步移除 3 项
- `b97fe05` lint: 建立 ruff 门控并清零（283→0：273 自动修复 + 6 手工）；剩余债务以 ignore 登记（BLE001×29 生产 blind-except，逐条收窄），pyproject.toml 门控配置落定
- `97ce92d` test: 引入 pytest-timeout，OCPP 套件 `@pytest.mark.timeout(20)` 此前被静默忽略，现真正生效

### Fixed
- `e5bf45e` fix(F7): test_heartbeat_loop_cancelled 未 mock httpx，导致测试间网络泄漏
- `e1b2698` fix(deps): 补 httpx + websockets 缺失依赖（自驱构建轮发现，此前 requirements 声明不全）
