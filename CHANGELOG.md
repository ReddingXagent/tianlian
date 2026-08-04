# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
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
