# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- jest coverageThreshold门限棘轮落地(高优卡清零, 构建维度例行清单"下一候选"首项): ops仓覆盖率原零断言——回归静默放行(F295同族静默最恶漂移), station(99/96/98/99)/user-app(78/70/77/78)均已配置唯ops缺 → package.json jest配置新增coverageThreshold.global 84/70/79/85, 实测84.24/70.93/79.6/85.91下取整形态(同款下取整惯例, 余量0.24/0.93/0.6/0.91); 变异验证(F251): M1 branches 70→71超实测 jest精确FAIL "threshold for branches (71%) not met: 70.93%", 还原diff零残留; 棘轮只升不降(F207), 余量<1不硬升先补分支覆盖(F278语义); jest --coverage 268绿32 suites全量复验
- eas.json构建期env↔.env.example模板对账守卫(F342, 第十八枚守卫, 构建维度例行清单"下一候选"落地): eas.json build.*.env(EAS云端构建期注入, EXPO_PUBLIC_*同样烤入bundle) ↔ .env.example(部署者照抄模板, 本地构建env来源) 原零断言 — 云端构建接入env后与本地构建内联env静默分叉: 同一份代码两个构建产物行为漂移, 部署者照模板配的本地env与云端产物不一致, 无任何报错(F295同族静默最恶漂移); F256管代码fallback↔模板双源, 本守卫管eas.json云端注入↔模板双源, 互补不重叠 → 新增 `scripts/check-eas-env.sh` 双不变量: A键登记(eas.json各profile env中EXPO_PUBLIC_*键⊆.env.example键清单) + B值级对账(已登记键 eas.json值==模板值, F256值级语义第三源扩展), 非EXPO_PUBLIC_*键(构建凭据类走EAS secrets)不要求登记模板——登记会与F256死键断言冲突(守卫间边界互斥已文档化); 基线守卫先行(F330形态): 当前三profile env均为空零命中, 门禁防未来env注入欠账, 提取空是合法态不FAIL; 缺输入(eas.json/.env.example)/解析失败/值非字符串均exit 1友好提示(F212); `npm run check:eas-env` 接入 CI check job + Makefile eas-env-check target(并入 check 链+.PHONY, 委托单一源, F250 guard-wiring 三源同步覆盖17 check:*守卫, ci-parity 23→24门控); 变异三档实测: ①M1a未登记键注入(EXPO_PUBLIC_FOO) exit 1精确拦A断言 ②M1b已登记键值漂移(EXPO_PUBLIC_API_URL→localhost:3000) exit 1精确拦B断言 ③M2 mv走.env.example缺输入 exit 1友好拦, 每档cp备份还原后基线 exit 0 + diff零残留; 全门复验: make check 十八守卫链 + tsc + lint 0/0 + jest 268绿
- README质量门控章节F186欠账清(文档轮另找产出, F319形态): 门控章节原只列基础四门且覆盖率旧值(83.62/71.65/77.34/85.39) → 补齐构建守卫族十七枚全清单表格(16 check:*脚本逐枚对账语义+F编号, 语义逐项取自Makefile注释实测, 另列bundle-size.sh F212+jest层appConfig.test.ts F244) + expo-doctor体检 + make ci-local全链构成 + ci-parity 23门控 + F250三源接线说明; 覆盖率段更新为全量口径实测84.24/70.93/79.6/85.91(F248口径, HEAD a4b13ad对齐status基线免重跑F229) + coverageThreshold未配现状声明(高优卡在办); 同源清F25/F33过期措辞三处(构建与部署"需EAS账号"/已知缺口行/Roadmap条目→08-05决策清零表述: 不需账号, APK直装分发, OTA延后发布候选期, F302守卫为门禁形态); docs-only变更不触发代码门控
- assets体积上限守卫(F334, 第十七枚守卫, F327死资产反向对账同源进阶): assets/ 磁盘体积膨胀原零门控 — 运维App走APK直装/二维码分发(F25/F33决策), 无商店侧体积审查兜底, 资产膨胀直接进APK与OTA差分包且纯静默(无任何构建报错); F327管磁盘⊆引用(死资产), 本守卫管体积不膨胀, 互补不重叠 → 新增 `scripts/check-asset-size.sh` 双断言: 单文件≤512KB + 总体积≤2048KB(当前基线 splash 48/icon 12/adaptive-icon 12 合计65KB, 守卫先行形态F330), 扫描不限扩展名(字体/lottie json等未来资产同样进包), 缺输入(assets/不存在)/提取空不放行(F212); `npm run check:asset-size` 接入 CI check job + Makefile asset-size-check target(并入 check 链+.PHONY, 委托单一源, F250 guard-wiring 三源同步覆盖16守卫, ci-parity 22→23门控); 变异两档实测: ①注入600KB探针文件(单文件超限档) exit 1精确拦 ②mv走assets/缺输入档 exit 1拦, 每档还原后基线 exit 0 + git status零残留; 全门复验: make check 十七守卫链 + tsc + lint 0/0 + jest 268绿
- assets磁盘↔引用源反向对账守卫(F327, 第十六枚守卫, 并发轮建树+接手轮CI接线落盘): assets/ 磁盘每个资产文件必须被至少一个引用源引用(引用源1: app.json 资产字段 icon/favicon/splash.image/adaptiveIcon.foregroundImage/backgroundImage; 引用源2: 代码 require assets/* 形态), 死资产=最恶漂移: 开发者误以为资产生效去修改(如换图标)而构建实际不读它, 发版后"图标没更新"排障失锚, 同时静默增大仓库体积; 与 jest appConfig.test.ts 正向断言(引用→磁盘存在, F309建树时确认)互补不重叠(F268反向补全形态) — 首跑即撞存量缺口: assets/favicon.png 无任何引用(app.json 无 favicon 字段, Expo原生app不消费favicon), 同源清退删除 → 新增 `scripts/check-unused-assets.sh` 断言磁盘文件全集⊆引用集合 + 引用源提取空不放行(F306活性断言) + 缺输入不放行(F212); `npm run check:unused-assets` 接入 Makefile unused-assets-check target(并入 check 链, 并发轮已接线)+CI check job(接手轮补接, 并发轮changeset漏CI侧→F250三源一致性会拦, 补接线后 guard-wiring 15 check:*守卫三源一致, ci-parity 21→22门控); 变异两档实测: ①app.json icon声明改名icon-x.png(声明侧值改名档) exit 1精确拦死资产 ②mv走app.json缺输入档 exit 1拦, 每档cp备份还原后基线 exit 0 + diff零残留; 全门复验: make check 十六守卫链 + tsc + lint 0/0 + jest 268绿
- .gitignore↔.easignore敏感排除超集守卫(F321, 第十五枚守卫): .gitignore 凭据类排除模式(.env/*.jks/*.keystore) ↔ .easignore(EAS云端构建上传范围的决定源) 是两条独立管线的同语义声明(F224族双源对账, 此处语义为超集而非相等), 只改.gitignore新增敏感排除而.easignore不同步即漂移: 本地git不见的凭据文件被EAS原样上传云端构建集群, 无任何报错(静默泄露, 最恶漂移形态) — 首跑即撞真实存量缺口: .easignore 三类凭据模式全缺, 存量同源修复补入 → 新增 `scripts/check-easignore-secrets.sh` 断言三类凭据模式 .gitignore 声明侧活性断言(F306防清单过期) + .easignore 超集覆盖断言, 缺输入不放行(F212); 同源清欠账: .easignore 死条目 .eslintrc.js(legacy配置名)→eslint.config.js(现仓flat config实际文件名); `npm run check:easignore-secrets` 接入 CI check job + Makefile easignore-secrets-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖14守卫, ci-parity 21门控含新守卫); 变异两档实测: ①删*.jks行 exit 1精确拦覆盖缺失 ②mv走.easignore缺输入 exit 1拦, 每档cp备份还原后基线 exit 0 + diff零残留; 全门复验: make check 十五守卫链 + tsc + lint 0/0 + jest 268绿
- versionCode↔buildNumber数值配对守卫(F315, 第十四枚守卫): app.json expo.android.versionCode(Play构建序号) ↔ expo.ios.buildNumber(App Store构建序号) 是同一语义的双源(F224族同语义双源值级), 发版必须两侧同步棘轮, 只改一侧→双平台二进制构建序号分叉, 排障/灰度对照失真(最恶=静默: 两侧各自构建全过, 商店版本号对账时才暴露); F288只断言两键存在性(合法正整数), 数值配对是盲区 → 新增 `scripts/check-build-number-parity.sh` 断言归一化(数字字符串正则同形)后精确相等+双侧≥1活性断言(F306防豁免吞断言)+缺输入不放行(F212); `npm run check:build-number-parity` 接入 CI check job + Makefile build-number-parity-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖13守卫, ci-parity 20门控含新守卫); 变异实测: versionCode 1→2 exit 1精确拦漂移, cp备份还原后基线 exit 0 + diff零残留; 同源清欠账: Makefile .PHONY 补登 engine-strict-check/expo-plugins-check/updates-channel-check(F308漏登欠账同源形态); 全门复验: make check 十四守卫链 + tsc + lint 0/0 + jest 268绿
- app.json品牌色双源漂移守卫(F309, 第十三枚守卫): splash.backgroundColor(启动屏背景) ↔ android.adaptiveIcon.backgroundColor(Android启动器图标背景) 是同一品牌色的同文件内双源声明(F224同族形态, appConfig.test.ts jest层未覆盖此键——先查jest覆盖面再建树F268), 只改一侧即漂移: 启动屏品牌蓝而图标背景另一色, 纯视觉静默漂移无任何构建/运行时报错 → 新增 `scripts/check-brand-color.sh` 断言两侧成对存在+hex归一化小写后相等, 任一侧缺失视为漂移或提取器盲区(本仓基线两侧均声明, F306活性断言形态), 缺输入不放行(F212); `npm run check:brand-color` 接入 CI check job + Makefile brand-color-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖12守卫, ci-parity 19门控含新守卫); 变异两档实测: ①adaptive色值漂移#ff0000 exit 1精确拦 ②删splash.backgroundColor键 exit 1精确拦缺失, 每档cp备份还原后基线 exit 0 + cmp零残留; 花絮: 本轮首棵候选(资产路径声明↔磁盘存在shell守卫)建树中撞 appConfig.test.ts jest层已有icon/splash/adaptiveIcon存在断言, 按F268(语义重叠保留jest层)整棵回退换题; 全门复验: make check 十三守卫链 + tsc + lint 0/0 + jest 268绿
- OTA更新通道双源成对守卫(F302, 第十二枚守卫): app.json expo.updates.url(运行时 expo-updates 轮询的更新端点, 执行侧) ↔ eas.json projectId(EAS 账号侧项目锚点, eas init/eas update 写入的身份标识) 原成对关系零断言 — 最恶漂移形态=半接线: 账号接入后 eas 侧有 projectId 而 updates.url 仍是脚手架占位(https://u.expo.dev/your-project-id)或反向, 更新包推往不存在的项目/无锚点可推, 设备端静默永不收到 OTA 更新(无报错只有"没有新版本"); 当前双占位=未接账号一致态(F25/F33决策: OTA延后到发布候选期), 放行但显式输出状态防误读为已接线 → 新增 `scripts/check-updates-channel.sh` 三形态断言: 双占位/缺失一致态 exit 0 + 半接线双向 exit 1 + 双真值时 url 尾段 uuid 必须==projectId(不等即漂移 exit 1), 占位形态识别(your-*/尖括号/xxx/example/placeholder/todo), 缺输入不放行(F212); `npm run check:updates-channel` 接入 CI check job + Makefile updates-channel-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖11守卫, ci-parity 18门控含新守卫); 变异六档实测: ①基线双占位 exit 0 ②eas注入projectId半接线 exit 1精确拦 ③url真值无projectId半接线反向 exit 1精确拦 ④双真值uuid不一致 exit 1精确拦 ⑤双真值一致 exit 0 ⑥mv走app.json缺输入 exit 1拦, 每档cp备份反向还原后基线 exit 0 + diff零残留; 全门复验: make check 十二守卫链 + tsc + lint 0/0 + jest 268绿
- expo.plugins↔package.json依赖双源成对守卫(F296, 第十一枚守卫): app.json expo.plugins(config plugin 声明侧, prebuild/export 按名加载) ↔ package.json dependencies+devDependencies(供给侧, 插件包必须真实安装) 原成对关系零断言 — 声明了插件而依赖缺失(或插件名拼写漂移)时 expo 加载 config plugin 静默跳过/延迟到 prebuild 才崩, 插件承载的原生配置(权限声明/AndroidManifest/Info.plist 注入)整体缺失, 上架/运行时才暴露 → 新增 `scripts/check-expo-plugins-deps.sh` 断言每个插件名(string 或 [name, props] 首元素)必在 deps∪devDeps, 未识别条目形态 loud fail, 反向(dep存在未声明plugin)因 expo-status-bar 等组件型包无需 config plugin 存在合法豁免不做断言, 缺输入不放行(F212); `npm run check:expo-plugins` 接入 CI check job + Makefile expo-plugins-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖10守卫, ci-parity 17门控含新守卫); 变异四档实测: ①注入无依赖插件声明(expo-camera) exit 1 ②未识别条目形态(object) loud fail exit 1 ③删依赖 expo-secure-store exit 1 ④删 expo.plugins 键缺输入 exit 1, 每档cp备份反向还原后基线 exit 0零残留; 全门复验: make check 十一守卫链 + tsc + lint 0/0 + jest 268绿 MAKECHECK_EXIT=0
- appVersionSource双源成对守卫(F288, 第十枚守卫, 首跑撞存量): eas.json cli.appVersionSource="local" 声明"版本号由本地 app.json 管理"(声明侧) ↔ app.json expo.android.versionCode/expo.ios.buildNumber(EAS 构建实际读取的执行侧) 原成对关系零断言 — 首跑即撞真实存量缺口: app.json 双键均缺失, EAS 本地版本管理无锚点, Play/App Store 递增版本号约束下首次上架/后续提交必静默撞车(对账守卫首跑撞存量第五验, F252/F277/F285族) → 新增 `scripts/check-app-version-source.sh` 断言 appVersionSource=local 时双键必为正整数成对存在, appVersionSource=remote 为合法替代形态放行, 未识别形态 loud fail, 缺输入不放行(F212); 存量同源修复: app.json 补 versionCode=1 + buildNumber="1"; `npm run check:app-version-source` 接入 CI check job + Makefile app-version-source-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖9守卫, ci-parity 16门控含新守卫); 变异两档实测: ①删 versionCode exit 1精确拦执行力缺失 ②appVersionSource local→remote exit 0合法替代放行, cp/sed 反向还原后基线 exit 0 + git diff 仅预期变更零残留; 全门复验: make check 十守卫链 + tsc + lint 0/0 + jest 268绿 MAKE-EXIT=0
- engines.node执行力双源漂移守卫(F282, 接手并发轮复验落盘): package.json engines.node(声明侧) ↔ .npmrc engine-strict=true(执行侧, F218加严) 是同一门控的双源, 原成对关系零断言, 任一侧单独变更即漂移且双向均静默失效(engine-strict被删/改false而engines仍在→npm默认EBADENGINE仅warning, 低版本Node静默装上依赖运行期才炸; engines.node被删而engine-strict仍在→死配置无声明可执行, F258反向形态) → 新增 `scripts/check-engine-strict.sh` 断言两侧成对存在+双方均缺整体缺失拦(缺输入不放行 F212), `npm run check:engine-strict` 接入 CI check job + Makefile engine-strict-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖8守卫); 变异两档实测: ①engine-strict=true→false exit 1精确拦静默失效 ②删engines.node exit 1精确拦死配置, 每档cp备份反向还原后基线 exit 0零残留; 接手复验全门: make check 八守卫链(含新守卫) + tsc + lint 0/0 + jest 268绿
- CI门控链↔ci-local双源漂移守卫(F274): .github/workflows/ci.yml 实际CI门控链(check+export两job的run步骤) 与 Makefile ci-local"模拟CI全流程"是同一语义的双文件声明, 原零断言, 任一侧单独变更即漂移(CI新增门控未同步ci-local→本地全绿≠CI绿的隐性漏测; ci-local多出门控→本地白跑误严) → 新增 `scripts/check-ci-parity.sh`: CI侧提取全部`- run:`步骤归一化(npm run X→X / npm test→test / ./scripts/X.sh→scripts/X.sh, npm ci为基础设施不计, 未识别形态loud fail防静默漏计), Makefile侧自ci-local递归展开前置目标至配方行同规则归一化, 双侧集合双向对账(缺输入/提取空/集合不等均exit 1); `npm run check:ci-parity` 接入 CI check job + Makefile ci-parity-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源同步覆盖7守卫); 变异四档实测: ①CI删lint步骤 exit 1精确拦 ②ci-local摘doctor exit 1精确拦 ③CI注入未识别形态(make mystery-step) loud fail exit 1 ④mv走Makefile缺输入 exit 1, 每档cp备份反向还原后基线 exit 0零残留; bash -n + YAML解析 + make -n 通过; 全门复验: make check 七守卫 + tsc 0err + lint 0/0 + jest 268绿
- 环境变量双源漂移守卫(F256, F255模式自edge-gateway移植): 运行时代码 process.env.EXPO_PUBLIC_* 读取键(权威源) ↔ .env.example 模板键清单(部署者照抄模板)原零断言, 任一侧单独变更即漂移(代码新增env键未登记模板→部署者漏配静默吃代码默认值; 模板残留代码已不读取的死键→误导); 且代码内联fallback字面量与模板值是同语义双源(EXPO_PUBLIC_*在expo export构建期内联, 构建时未设env→fallback即生产值), 单独改任一侧即漂移 → 新增 `scripts/check-env-defaults.sh` 双向对账键集合 + fallback值==模板值断言(缺输入/提取空/不等均exit 1, F212), `npm run check:env-defaults` 接入 CI check job + Makefile env-defaults-check target(并入 check 链, 委托单一源, F250 guard-wiring 三源一致性自动覆盖); 变异四档实测: ①基线 exit 0(1键双向一致+fallback值吻合) ②api.ts 注入未登记键 EXPO_PUBLIC_ZZZ_MUT exit 1 精确拦 ③.env.example 追加死键 ZZZ_DEAD_KEY exit 1 精确拦 ④fallback值 .166→.167 漂移 exit 1 精确拦 ⑤mv 走 .env.example 缺输入 exit 1 拦, 每档 sed/mv 反向还原后基线 exit 0 + git diff 零残留(F231铁律); bash -n + YAML解析 + make -n 通过; 全门复验: tsc 0err + lint 0/0 + jest 268绿
- 守卫接线三源一致性守卫(F250): 每个 check:* 守卫的接线是三份独立声明——package.json scripts 的 check:* 键(声明侧/权威源) ↔ Makefile check 链(经 *-check target 委托) ↔ ci.yml check job 步骤, 只改一侧即漂移(新增守卫脚本漏接 CI/Makefile=守卫存在但永不执行的假门控 F186教训; CI/Makefile 引用已删脚本=悬空引用), 原零断言 → 新增 `scripts/check-guard-wiring.sh` 三侧集合双向对账(声明侧↔Makefile 侧 + 声明侧↔CI 侧, 缺输入/提取空均 exit 1 不放行 F212), `npm run check:guard-wiring` 接入 CI check job + Makefile guard-wiring-check target(并入 check 链, 委托单一源); 本守卫自身也在对账范围内(守卫的失效条件也要门控 F236); 变异四档实测: ①基线 exit 0(4 守卫三源一致) ②package.json 侧新增未接线 check:zzz-mut exit 1 双侧精确拦 ③CI 侧删接线 exit 1 精确拦 ④Makefile check 链摘除 exit 1 精确拦 ⑤mv 走 Makefile 缺输入 exit 1 拦, 每档反向还原后基线 exit 0; 花絮: 首版 awk 单遍顺序扫描撞 check 链声明在文件后部/target 定义在前→空提取假阴性, 改 END 块两阶段解析; bash -n + YAML 解析 + make -n 通过; 全门复验: tsc 0err + lint 0/0 + jest 268绿
- app.json 构建配置回归守卫(移植 user-app F179/F196 同型, 接手并发轮复验落盘): platforms 限定 android+ios(防误挂 web) / plugins↔deps 双向对账(每个 plugin 必有已装 dep, 已知原生模块 expo-secure-store+expo-asset 必声明 plugin, F196 反向静默缺口) / android.package↔ios.bundleIdentifier 应用标识同语义双源一致(F224 同族同文件内形态) / icon+splash+adaptiveIcon 资产文件存在断言 — 新增 `src/__tests__/appConfig.test.ts`(jest 全量跑自动接入 CI check job, 零额外接线); 变异三档实测: ①platforms 加 web 1 failed 精确拦 ②android.package 单侧改名 1 failed 精确拦 ③合法移除 expo-asset plugin(JSON 保持有效) 1 failed 精确拦, 每档 perl/sed 反向还原后基线 5/5 + git diff 零残留; 接手复验四门全走: tsc 0err + jest 263→268绿(32 suites) + lint 0err/0warn; 花絮: 首次 mut3 用行删除法撞出尾逗号破坏 JSON(suite 加载失败 Tests 0, 假阴性)→重做为合法 JSON 变异档(F236 花絮同型: 变异档须先核实目标结构)
- node版本双源漂移守卫(F237): engines.node(package.json, .npmrc engine-strict强制侧 F218) 与 CI setup-node node-version(.github/workflows/ci.yml 两 job) 是同一语义的双源, 只改一侧即漂移(engines抬高CI未跟上→CI npm ci engine报错; CI降级engines未跟上→本地装不上依赖/行为分叉), 原零断言 → 新增 `scripts/check-node-version.sh` 提取 engines 最低主版本对账每个 workflow 的 node-version(多 job 逐个断言; engines/node-version/workflows 缺输入均 exit 1 不放行), `npm run check:node` 接入 CI check job + Makefile node-check target(并入 check 链, 委托单一源); 变异四档实测: ①基线一致 exit 0(双 job 逐个过) ②CI node-version 20→18 exit 1精确报漂移 ③engines >=20→>=22 exit 1精确报漂移 ④移除 workflows 目录 exit 1缺输入拦 ⑤恢复 exit 0; bash -n + YAML解析断言通过; 全门复验: tsc 0err + lint 0/0 + jest 263绿
- 路径别名双源漂移守卫(F231): tsconfig.compilerOptions.paths 与 package.json jest.moduleNameMapper 是同一语义的双源(tsc侧 vs 测试侧解析源), 只改一侧即漂移(tsc与jest解析分叉: 一侧通过一侧报错) → 新增 `scripts/check-alias-config.sh` 断言两侧别名集合+目标目录一致, `npm run check:alias` 接入 CI check job + Makefile alias-check target(并入 check 链, 委托单一源); 变异四档实测: ①基线一致 exit 0 ②jest目标漂移src2 exit 1精确报漂移 ③tsconfig单侧新增别名 exit 1精确报缺失 ④恢复 exit 0; YAML解析断言通过; 全门复验: tsc 0err + lint 0/0 + jest 263绿
- 版本双源漂移守卫(F224): package.json.version 与 app.json.expo.version 同语义双源, 发布 bundle 以 app.json 为准 — 发版只改一处即漂移(线上版本与仓内声明不符, 排障/灰度对照失真), 原无任何门控 → 新增 `scripts/check-app-version.sh` 断言两侧一致, `npm run check:version` 接入 CI check job + Makefile version-check target(并入 check/ci-local 链, 委托单一源); 变异三档实测: ①基线一致 exit 0 ②app.json 版本变异 9.9.9 exit 1精确报漂移 ③恢复 exit 0; bash -n + YAML解析断言通过; 全门复验: tsc 0err + lint 0/0 + jest 263绿
- engines门控强制(F218): package.json `engines.node>=20` 原仅为声明 — npm默认对EBADENGINE只警告不拦截, Node 18/16本地`npm ci/install`+构建无声通过(声明的门控=假门控, F206同族) → 新增 `.npmrc` 设 `engine-strict=true`, npm ci/install在低版本Node直接失败; CI两job的npm ci读项目.npmrc自动生效, 零调用点改动(F206单一源模式); 变异实测四档: ①正常engines exit 0 ②变异`>=99`+engine-strict exit 1(EBADENGINE精确报错) ③恢复后exit 0 ④对照移除.npmrc+变异engines exit 0无声放行(证明缺口真实); 全门复验: tsc 0err + lint 0err/0warn + jest 263绿

### Fixed
- bundle-size门控单平台静默漏测(F212): 原逻辑导出目录缺失即"跳过"返回0 — 只导出android没导ios时门控照样通过, ios bundle超限无声放行 → 改为缺目录返回2, 单平台缺失/双缺均FAIL(门控要求双平台齐验); 变异三档实测: 双平台齐在exit 0 / 单缺exit 1(新拦截) / 双缺exit 1
- F206遗留清零: CI export job与Makefile export-android/export-ios仍为裸 `npx expo export` → 全部委托 `npm run build:android/build:ios -- --output-dir ...`(参数透传); 验证: YAML结构断言(新调用点在位/裸npx清零/timeout与artifact保留) + make -n委托确认 + 真实android导出实测2.19MB与基线一致

### Changed
- 构建/测试/体检调用点单一源收敛(F206, F195模式): CI check job原为裸 `npx tsc`/`npx jest`/`npx expo-doctor` 绕过 package.json scripts(参数漂移: npm test无--coverage、Makefile与CI各一套) → 全部委托 npm scripts(`npm run typecheck` / `npm test -- --coverage --ci` / `npm run doctor`, 新增doctor script); Makefile build/test/doctor同步改委托; 附带修复门禁非确定性: expo-doctor原靠npx隐式下载无版本钉住(每次可能拉不同版本) → 钉为devDependency ^1.20.1, lockfile可复现; 验证: YAML解析+结构断言(新调用点在位/旧npx调用点清零/timeout保留) + tsc 0err + jest 263绿(经新路径, coverage实测stmts84.24%/branches70.93%/funcs79.6%/lines85.91%) + lint 0err/0warn + doctor 18/18 + make -n委托确认

### Changed
- lint门限补齐: `npm run lint` 补 `--max-warnings 0`(此前为裸 `eslint .`, 新增warning会无声通过 — F195同型门限漂移); Makefile lint与CI均已委托 `npm run lint`, 单点修改即全链路生效(调用点单一源); 变异测试实证: 纯warning探针(未用局部变量)无门限exit 0放行 → 加门限exit 1拦截, 清理后exit 0; bundle-size门控同轮变异实测: 4MB→FAIL(exit 1)/3MB→WARN(exit 0)/2MB→OK 三档全对
- CI健壮性加固: ①两job补 `timeout-minutes`(check=15/export=20) — 此前无超时, 挂死的export最多吃满GitHub默认6h runner; ②export job补 `upload-artifact`(always, 保留7天) — bundle-size回归/导出异常时可直接下载双平台hbc+资产取证, 门控失败也留现场(if: always); ③YAML解析+结构断言校验通过(timeout/artifact字段实测确认)

### Fixed
- bundle-size.sh 平台识别bug: `find | head -1` 不区分平台子目录, 同目录双平台(如 `dist/`)时 ios 误报 android 体积 → 改按 `_expo/static/js/<platform>/` 定位, 兼容旧布局单hbc兜底; 实测 `bundle-size.sh dist dist` android 2.19MB / ios 2.18MB 正确区分
- F167: `npm run build` 实际必挂 — `expo export` 默认含 web 平台但项目无 react-native-web/react-dom 依赖；app.json 加 `platforms: ["android","ios"]` 并移除无用的 web.favicon 配置，实测 build 全绿（android 2.3MB / ios 2.29MB）

### Changed
- expo-doctor 接入门禁自动化: CI check job 增加 `npx expo-doctor` 步骤 + Makefile 新增 `make doctor` 目标并接入 ci-local（此前 doctor 仅手动体检, 版本漂移无回归防护）; bundle-size.sh 门控加固 — 双平台导出目录都缺失时由静默通过改 FAIL（门控无对象可测不应放行）; 实测 doctor 18/18 全绿 + bundle-size 正常路径 android 2.19MB / ios 2.18MB 不受影响
- 构建依赖健康检查: 引入 `npx expo-doctor` 作为构建维度体检项 — 撞出 eslint-config-expo 与 SDK 版本漂移(doctor期望SDK52→~8.0.1); 实测8.0.1为legacy eslintrc配置(无 `/flat` 导出, 与本仓ESLint 9 flat config不兼容, require直接报错) → 保留57.0.1(flat原生, lint实测0 err/0 warn), package.json 钉 `expo.install.exclude: [eslint-config-expo]` 并向doctor声明该豁免, doctor复验18/18全绿
- Makefile ci-local 补 export-ios（原仅 android, 本地模拟CI漏掉iOS体积门控）; lint 目标改 `npm run lint` 与 CI 对齐（原 `eslint src/ --ext` 范围不一致）; clean 补删 `dist/`（npm run build 产物目录）

### Added
- scripts/bundle-size.sh: JS bundle 体积门控（WARN>2.75MB / FAIL>3.5MB；基线 android 2.19MB / ios 2.18MB hbc）
- Makefile: 新增 bundle-size 目标并接入 ci-local；export 产物体积可门禁
- GitHub Actions CI: export job 增加 bundle-size 门控步骤
- Makefile: 本地构建/检查/导出快捷命令 (help/install/dev/build/test/lint/check/ci-local/clean)
- GitHub Actions CI: .github/workflows/ci.yml 两阶段流水线 (check→export)
- DEPLOYMENT.md: 环境变量使用说明 + Makefile/CI 文档 + OTA 更新步骤

### Changed
- README 质量门控数据更新：243 测试全绿，eslint 0 err / 0 warn，覆盖率 83.62%
- README Roadmap 更新：F17 标记解决，新增 F69/F70/F92 等覆盖薄弱点记录

### Added
- 文档：screen 测试覆盖率明细表（InspectionDetailScreen 57.4% ~ DiagnosisScreen 100%）

### Fixed
- F79: 移除 40 处未使用的 React 默认导入（`4c8a8e7`）
- F86: eslint 警告清零，16→0（`ff9866d`）
- api.ts 全部 `any` 类型已消除，生产代码零 any（`2d462f0`）

### Added (前期)
- 部署链路补齐：eas.json（development/preview-APK/production 三档 profile）
- 品牌占位 assets：icon/adaptive-icon/splash/favicon（蓝底白字 TL，待设计稿替换）
- README 新增「构建与部署」章节（OTA 导出 / EAS 构建命令 + 已知缺口 F22/F24/F25）
- 项目 README：技术栈、功能模块、质量门控、目录结构、Roadmap 缺口说明
- 本 CHANGELOG 文件

## [1.0.0] - 2026-07-30

### Changed
- 移动端依赖对齐 Expo SDK 52：react-native 0.76.6 → 0.76.9（`01fe602`）

### Added
- 建立 eslint 门控（expo flat config），修复 3 处 hook 真问题（`480d0ff`）
- 补 LoadingSpinner / WorkOrderCard 组件测试，coverage 收集范围显式化（`c0a2922`）

### Fixed
- 补 expo-asset 直接依赖，修复 expo export Metro 找不到包（`35c6f84`）

## [0.2.0] - 2026-07

### Added
- B1 工单全流程对齐真云端 API 契约（`8878b6c`）

## [0.1.0] - 2026-07

### Added
- P1 完成：工单流转 / 扫码 / 故障诊断 / 知识库 / 巡检（`e5fff15`）
- 项目初始化（Expo RN + TS）
