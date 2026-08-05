# Changelog — tianlian-user-mp

格式参考 Keep a Changelog。本仓为微信小程序用户端。

## [Unreleased]

### Added
- setData 负载体积静态守卫（F317）：setData 序列化成本与负载体积线性相关，微信官方性能指南要求负载“小而精”；F298 已覆盖频次反模式（循环体内/相邻对），但**单次负载体积本身**零静态断言——人肉评审对“字面量塞太多”没有客观标尺。不变量（内联对象字面量调用点）：A. 顶层静态键数 ≤ 8（键多 = 一次调用搅动多个视图区域，应拆分/改 path 形式）；B. 字面量源码长度 ≤ 512 字符（序列化体积直接代理）。阈值依据：全仓实测基线 maxKeys=4 / maxLen=214（72 处内联字面量），取 ~2x 余量作棘轮——现状全绿，体积膨胀一半即触发评审。含展开（...x）/计算键（[k]:）的字面量键数不可信→只查 B 不查 A（不误报）；非字面量调用（setData(变量)）体积不可静态判定→豁免（F298 频次族已覆盖其形态）。提取基线：字符级六态状态机剥注释+掩字符串内容保长度（行号不错位），括号配平/字面量定位只信任掩码文本。活性断言（F306/F308/F311 形态）：扫描 js≥1 + setData 调用点≥1 + 内联字面量≥1（本仓基线 21 js / 76 调用点 / 72 字面量）。扫描 app.js + pages/components/services/utils/config 全部 .js，__tests__ 豁免（F292 口径）。缺输入（零应用 js）/调用点为零/字面量为零（提取器失效信号）→ exit 1（F212 不放行）。npm run check:setdata-payload 接入 CI check job + Makefile check 链（setdata-payload-check，委托单一源，F250 自动覆盖接线一致性）。摸底现状 = 守卫先行零命中；变异三档实证（M1 favorites.js 注入 10 键字面量 exit 1 精确拦 / M2 注入 588 字符长字面量 exit 1 精确拦 / M3 tmp 骨架缺输入 exit 1，cp 备份还原 diff 零残留）；eslint 0err/0warn + jest 230 绿 + make check 十三守卫全绿复验；user-mp 对账守卫族十三枚（F246/F252/F240/F258/F264/F270/F277/F284/F292/F298/F305/F311/F317）
- JSON 配置键白名单对账守卫（F311）：微信小程序对 app.json/页面 json/组件 json 中的未知键一律**静默忽略**——拼写错误（navigationBarTitleTxt）编译零报错、上传零报错，但运行时该配置永不生效，与 F295 同族"静默 no-op 最恶漂移"；mp 无 tsc/schema 校验，此前零静态断言。不变量：A. app.json 顶层键 ⊆ APP_KEYS，window/tabBar(+list 项)/networkTimeout 嵌套键各守白名单，permission 键必须 scope.* 前缀，preloadRule 键必须是已注册页路径；B. 页面 json 顶层键 ⊆ PAGE_KEYS；C. 组件 json（component:true）顶层键 ⊆ COMPONENT_KEYS；D. 枚举值字段值域校验（navigationBarTextStyle ∈ white|black、backgroundTextStyle ∈ dark|light、navigationStyle、tabBar.position/borderStyle、style ∈ v2|v3、lazyCodeLoading——非法值静默回退默认）；E. tabBar.list[].pagePath ⊆ pages 注册集（跨源对账）；F. 未知 json 配置文件（非豁免清单）= 漂移信号不放行。活性断言（F306/F308/F309 形态）：扫描配置文件数≥2 + 观测键集合非空，防豁免清单吞断言。豁免清单（自有 schema）：package.json/package-lock.json（npm）、project.config.json/project.private.config.json（开发者工具）、sitemap.json、node_modules/miniprogram_npm/coverage/__tests__（F292 口径）。缺输入（app.json 缺失/解析败/pages 为空）→ exit 1（F212 不放行）。npm run check:json-keys 接入 CI check job + Makefile check 链（json-keys-check，委托单一源，F250 自动覆盖接线一致性）。摸底现状 = 守卫先行零命中（15 配置文件 / 4 观测键全部命中白名单）；变异五档实证（M1 页面 json 拼错键 exit 1 / M2 app.json 未知顶层键 exit 1 / M3 枚举非法值 exit 1 / M4 未知 json 文件 exit 1 / M5 app.json 缺输入 exit 1，cp 备份还原 diff 零残留）；eslint 0err/0warn + jest 230 绿 + make check 十二守卫全绿复验；user-mp 对账守卫族十二枚（F246/F252/F240/F258/F264/F270/F277/F284/F292/F298/F305/F311）


- wxs 视图层隔离双向对账守卫（F305，接手轮三档变异当场命中落盘）：wxs 是小程序视图层专属脚本语言（独立运行时，仅 wxml 可消费），与逻辑层 js 完全隔离，平台零编译期交叉断言，三类静默漂移：①孤儿 wxs 文件：实体写了但无 wxml <wxs src> 声明引用→永不执行纯死代码（F284 孤儿组件/F258 孤儿页同族反向盲区）②悬空声明：wxml <wxs src> 指向不存在文件→开发工具编译报错但 CI/上传链路无编译步骤则静默通过，渲染侧拿不到 module③层级越界：逻辑层 js require/import .wxs→wxs 不在 js 运行时里，构建可能过但运行时炸/产物异常。不变量（双向成对）：A. wxs 实体集 ⊆ <wxs src> 声明解析集（无孤儿）；B. 声明解析集 ⊆ 实体集（无悬空）；C. js require/import .wxs 调用点 = 0（视图层脚本禁逻辑层引用）。提取口径：实体侧全仓 walk .wxs；声明侧全仓 walk .wxml 剥 <!-- --> 注释后提取 <wxs src>（内联 <wxs module> 无文件不参与对账），src 路径归一化（/ 开头=项目根相对，否则声明方目录相对，http(s):// 外部引用豁免计数）；js 侧字符级状态机剥注释保字符串，扫 app.js+pages/components/services/utils/config 全部 .js，__tests__ 豁免（F292 口径）。零态合法性：本仓当前未使用 wxs（0 实体/0 声明/0 越界）是合法一致态，exit 0 且显式输出防误读（F302 形态，14 wxml/21 js 扫描）；缺输入（零 wxml 文件）/任一断言败均 exit 1（F212 不放行）。npm run check:wxs-isolation 接入 CI check job + Makefile check 链（wxs-isolation-check，委托单一源，F250 自动覆盖接线一致性）；变异三档实证（M1 孤儿 wxs 实体注入 exit 1 精确拦 / M2 悬空 <wxs src> 声明注入 exit 1 精确拦 / M3 app.js require .wxs 越界注入 exit 1 精确拦，cp 备份还原 diff 零残留）；eslint 0err/0warn + jest 230 绿 + make check 十一守卫全绿复验（coverage 98.07/85.76/98.33/98.91 与 README 声明逐项吻合）；user-mp 对账守卫族十一枚（F246/F252/F240/F258/F264/F270/F277/F284/F292/F298/F305）
- setData 性能反模式静态守卫（F298）：小程序 setData = 逻辑层→渲染层跨线程序列化 + diff + 视图重排，是渲染性能第一瓶颈（微信官方性能指南反复强调避免频繁/大量 setData）；小程序无 tsc/编译期约束，两类高频反模式零静态断言：①循环体内 setData（for/while/do-while/数组迭代方法回调）：N 次迭代 = N 次跨线程序列化+渲染（渲染风暴），列表页初始化/批量操作最易踩，正确形态是循环外组装对象一次性 setData；②相邻同步 setData 对：两次调用间无异步/渲染间隙完全可合并，省一次跨线程往返。两类都属"功能正确但性能静默劣化"，人肉评审难穷尽，自动化为门禁。不变量：A. .setData( 调用点集 ∩ 任一循环体区间 = ∅（嵌套循环按各层独立报告，每层都是真渲染放大）；B. 任一 setData 调用的紧邻下一语句不得是另一 setData。循环体区间覆盖 for/while 括号配平语句体（花括号块或单语句）、do 块体、forEach/map/filter/some/every 回调体（花括号块或箭头表达式体）。提取基线：字符级六态状态机（code/line/block/sq/dq/tq）同步剥注释+掩字符串内容保长度（行号不错位），结构扫描只信任掩码文本——字符串内的括号/分号/setData 字样不参与结构判定不误报。扫描 app.js + pages/components/services/utils/config 全部 .js，__tests__ 豁免（F292 口径——测试夹具是断言脚手架不是出厂代码）。缺输入（零应用 js）/setData 调用点为零（提取器失效信号）/任一断言败均 exit 1（F212 不放行）；npm run check:setdata-perf 接入 CI check job + Makefile check 链（setdata-perf-check，委托单一源，F250 自动覆盖接线一致性）。摸底现状 = 守卫先行零命中（76 setData 调用点 / 22 循环迭代体区间 / 21 js 扫描）；变异四档实证（M1 for 循环体 setData 注入 favorites.js exit 1 精确拦 / M2 相邻 setData 对注入 exit 1 精确拦 / M3 字符串+注释内 setData 注入误报抵抗 exit 0 / M4 tmp 骨架缺输入 exit 1，cp 备份还原零残留基线 exit 0）；eslint 0err/0warn + jest 230 绿 + make check 十守卫全绿复验；user-mp 对账守卫族十枚（F246/F252/F240/F258/F264/F270/F277/F284/F292/F298）
- 请求出口↔URL声明单一源对账守卫（F292）：小程序网络栈无编译期约束，wx.request 随处可调、URL 字面量随处可写，而本仓既定架构是 services/api.js 唯一请求出口（统一 token 注入/超时/重试/{code,message,data} 信封解析）+ config/index.js 唯一 URL 声明源（dev/staging/prod 三环境 API_BASE_URL），双单一源零断言。两类静默漂移：①出口旁路：页面直调 wx.request/uploadFile/downloadFile→绕过 token 注入（鉴权静默失败）+绕过信封解析（裸 response 误当 data）+绕过统一超时/重试，真机域名白名单校验面扩大②URL 多源：http(s):// 字面量散落 api/config 之外→环境切换时硬编码地址不跟随，线上静默打错端点（与 F89 HTTPS 漂移同族前置）。不变量（双单一源成对）：wx.request/uploadFile/downloadFile 调用点集 ⊆ services/api.js；http(s):// 字符串字面量出现点集 ⊆ config/index.js；wx.requestPayment 是支付 API 非 HTTP 出口，整词匹配排除；注释内 URL 用字符级状态机（code/line/block/sq/dq/tq 六态）剥离豁免（字符串内容保留，scan.js 文档注释不误报）。扫描 app.js+pages/components/services/utils/config 全部 .js，__tests__ 豁免（首跑撞出 api.test/perf.test/config.test 六处合法夹具字面量——测试钉死字面值是断言前提不是漂移，同 commit 豁免；与 F270 口径差异已注记）。HTTPS 方案级断言留白：prod 现为 http://，微信正式版强制 HTTPS（F89），升级依赖云端 https 域名就绪（大圣侧），届时本守卫加方案断言同 commit 收敛。缺输入（零应用js）/任一集合为空（提取器失效信号）/任一断言败均 exit 1（F212 不放行）；npm run check:request-source 接入 CI check job + Makefile check 链（request-source-check，委托单一源，F250 自动覆盖接线一致性；顺带修 .PHONY 漏登 orphan-components-check 存量缺口）。摸底现状=守卫先行零命中（1 出口调用点/3 URL 字面量/1 注释豁免，21 js 扫描）；变异四档实证（出口旁路注入 profile.js exit 1 精确拦 / URL 多源注入 api.js exit 1 精确拦 / 注释 URL 注入豁免 exit 0 / tmp 骨架缺输入 exit 1，cp 备份还原零残留基线 exit 0）；eslint 0err/0warn + jest 230 绿 + make check 九守卫全绿复验；user-mp 对账守卫族九枚（F246/F252/F240/F258/F264/F270/F277/F284/F292）

### Added
- 孤儿组件反向对账守卫（F284）：check-mp-structure.js 只挡正向（usingComponents 引用必须可解析+四件套+component:true），反向是盲区——组件被页面删除引用后实体残留=死组件，白占小程序包体积（主包寸土寸金，F90 分包压力同源）+增大上架审核扫描面。不变量（单向子集反向补盲，F258 孤儿页/F264 死handler 同族）：组件实体集（json 含 component:true）⊆ usingComponents 引用解析集；引用侧扫描 pages/+components/ 全部 json+app.json，绝对/相对路径归一化为项目根相对无扩展路径（与 check-mp-structure 同口径），plugin:// 豁免。缺输入（app.json 缺失）/实体集为空（提取失效信号）/断言败均 exit 1（F212 不放行）；npm run check:orphan-components 接入 CI check job + Makefile check 链（orphan-components-check，委托单一源，F250 自动覆盖接线一致性）。摸底现状=3 实体 6 引用全吻合（守卫先行，F258 同型）；变异四档实证（孤儿注入 tmp-mut exit 1 精确拦 / empty 引用全删 exit 1 精确拦，node 操作 JSON 保证变异合法——sed 删行留尾逗号会撞 JSON 非法分支非目标断言 / 相对路径引用归一化 exit 0 / 备份还原零残留基线 exit 0）；eslint 0err/0warn + jest 230 绿 + make check 八守卫全绿复验；user-mp 对账守卫族八枚（F246/F252/F240/F258/F264/F270/F277/F284）

### Added
- 隐私API↔app.json声明双向对账守卫（F277）：微信 2022 隐私接口整改后，涉及隐私的 wx.* API 必须在 app.json requiredPrivateInfos 中声明，否则真机运行时直接拒绝调用（fail: privacy permission is not allowed）——app.json 声明侧与代码调用侧是典型双源，无编译期/静态断言，两类静默漂移：①调用未声明：新增 wx.getLocation 类调用忘补声明→开发工具不报（宽松），真机运行时 fail 功能静默挂（最恶形态=提审通过线上才炸）②声明未调用：requiredPrivateInfos 残留无人调用的隐私项→隐私协议多列敏感权限，审核风险+用户信任成本+接手者误判。不变量（双向成对，F246/F258、F252/F264、F270 同族）：正向 used(隐私API)映射值 ⊆ requiredPrivateInfos 声明；反向声明 ⊆ used 映射值；附加（仅正向）调用 API 隐含授权 scope 必须在 app.json permission 块有非空 desc（微信强制：无 desc 首次授权弹窗直接报错；scope 反向不断言，desc 是零运行时成本文案）。API→info 映射单一源：getLocation/getFuzzyLocation/chooseLocation/choosePoi/startLocationUpdate/startLocationUpdateBackground/onLocationChange（归并后台定位）/chooseAddress/chooseInvoiceTitle；openLocation 等不采集隐私信息的 API 不入映射（声明反而是错）。扫描 app.js+pages/components/services/utils/config 全部 .js（排除 node_modules/scripts/coverage，与 F270 同口径）。缺输入（app.json 缺失/解析败、零应用 js）/任一方向断言败/scope 缺 desc 均 exit 1（F212 不放行）；npm run check:permission-apis 接入 CI check job + Makefile check 链（permission-apis-check，委托单一源，F250 guard-wiring 自动覆盖接线一致性）。**首跑即撞出存量缺陷（F252 最高价值形态）：chooseLocation 已声明但全仓零调用=死隐私声明，同 commit 移除**；变异三档实证（清空声明→调用未声明 exit 1 精确拦 / 重注入 chooseLocation 死声明 exit 1 / scope.userLocation desc 置空白 exit 1，python 链式变异+逐项精确还原，app.json 最终 diff 仅 chooseLocation 移除一处零格式噪音；**教训：python json.dump 改 app.json 会重排行内数组为多行，同文件有合法未提交改动时还原须精确控制 diff 面**）；eslint 0err/0warn + jest 230 绿复验；user-mp 对账守卫族七枚（F246/F252/F240/F258/F264/F270/F277）

### Added
- storage键生命周期双向对账守卫（F270）：F240 只守 auth 层双源（app.js boot恢复 ⊆ api.js 登录写入）且为单向，反向摸底撞出 api.js 侧 favorites 键 app.js 从不触碰——同层单向子集无法表达全仓 storage 键完整生命周期，升维为全仓双向对账。漂移场景：storage 键名全仓字面量散布（无集中声明），写侧(set)与读侧(get)分源硬编码——①死写（set后全仓无人get）：残留数据永久占位，登出/清缓存路径漏清→换账号后旧数据静默串号（最恶形态=隐私残留）②孤儿读（get但全仓无人set）：读取永远落空走fail/默认值，功能静默降级零报错。不变量（双向成对，F246/F258 与 F252/F264 同族）：keys(get) ⊆ keys(set) ⊆ keys(get)；remove 键不参与断言（清理未写入的键是无害 no-op）仅计数报告；提取与 F240 同源双形态（首参字面量+异步对象 key 属性），扫描 app.js+pages/components/services/utils/config 全部 .js（排除 node_modules/scripts/coverage）。缺输入（零应用js）/任一方向集合为空（提取器失效信号）/任一方向断言败均 exit 1（F212 不放行）；npm run check:storage-keys 接入 CI check job + Makefile check 链（storage-keys-check，委托单一源，F250 guard-wiring 自动覆盖接线一致性）；摸底现状=零死写零孤儿读（favorites/scanHistory/station_filter/token/userInfo 五键双向完全吻合，29 js 扫描，守卫先行防未来漂移，F258 同型）；变异四档实证（死写注入 mutprobe270_dead exit 1 精确拦 / 孤儿读注入 mutprobe270_orphan exit 1 精确拦 / remove-only 注入豁免 exit 0 / 对象形态 setStorage({key:...}) 提取命中，备份还原零残留基线 exit 0）；eslint 0err/0warn + jest 230 绿 + make check 六守卫全绿复验

### Added
- 死handler反向可达性双源对账守卫（F264）：F252 只挡正向"wxml绑定⊆js方法集"（绑定引用不存在方法=点击静默失效），反方向"js方法既无任何wxml绑定也无js调用"零断言——重构改名/删wxml绑定后 js 方法残留=死handler（小程序无tsc编译期零拦截，死方法累积增大维护面与误读成本）。不变量（单向子集，F246/F258 同族反向补盲）：Page 顶层方法键/Component methods 键 ⊆ 同目录wxml绑定名集 ∪ 同文件this|self|that调用引用集；生命周期/框架键白名单排除（onLoad/data等15键）；wxml整词出现（覆盖{{}}动态绑定名/data驱动场景）计数不拦；提取口径与 check-wxml-handlers.js 完全同源（单口径复制，F258模式）。同源修复：collectKeys 键提取撞出两处提取缺陷并修复——①方法简写 key(a,b){}/箭头值 key:(a)=>{} 的参数列表在括号内，其逗号/标识符被误当键（parens 深度跟踪修复，变异实证：station-card 注入 mutprobe264(xyzparamf264){}+wxml 绑定 xyzparamf264 → exit 1 精确拦，证明参数不再入键集）②键名前任意空白致整块键集提取失效（readKeyAt 单入口重构，非键字符回落主循环不清 wantKey）；配对js双命名惯例 page=同名js/component=index.js（接手复验撞出原只认同名js致 components 层漏扫）。缺输入（配对js无Page/Component块）/方法集提取空/断言败均 exit 1（F212 不放行）；npm run check:dead-handlers 接入 CI check job + Makefile check 链（dead-handlers-check，委托单一源）；摸底现状=零死handler（13 js / 83 候选方法，守卫先行防未来漂移，F258 同型）；变异三档实证（scan.js 注入死方法 exit 1 精确拦+改绑既名方法立即成孤儿被拦=灵敏度实证 / pages 下注入无Page块js缺输入 exit 1 / wxml补绑即豁免 exit 0，sed 反向还原后基线 exit 0，F231 铁律禁 git checkout）；eslint 0err/0warn + jest 230 绿复验

### Added
- 孤儿页面反向可达性双源对账守卫（F258）：F246 只挡正向“跳转目标⊆注册页”（跳到未注册页），反方向“注册了但无任何入口的死页面”零断言——新注册页面未写导航入口=用户永远无法到达（功能静默不可用）/删除或改名全部跳转调用点但保留注册=孤儿页（死代码+包体膨胀）/tabBar 移除某页但 pages 保留即成孤儿。不变量（单向子集，F240/F243/F246 同族反向）：注册页集 ⊆ 静态导航目标集 ∪ tabBar 页集；提取逻辑与 check-nav-targets.js 同款单一口径（query/${}截断取静态前缀，纯动态 url 计数不豁免断言，F212）；缺输入/注册集空/可达集空/断言败均 exit 1（F212 不放行）；npm run check:orphan-pages 接入 CI check job + Makefile check 链（orphan-pages-check，委托单一源，F250 guard-wiring 自动覆盖接线一致性）；摸底现状=零孤儿（11 注册页 ⊆ 10 静态目标 ∪ 4 tabBar 页，守卫先行防未来漂移，F231 同型）；变异三档实证（coupons 双导航入口改名 exit 1 精确拦 / app.json tabBar 移除 profile exit 1 精确拦 / mv 走 app.json 缺输入 exit 1，sed 反向还原后基线 exit 0，F231 铁律）；eslint 0err/0warn + jest 230 绿复验
- WXML事件绑定↔JS方法定义双源对账守卫（F252）：wxml 事件绑定（bindtap/catchtap/bindinput... 调用侧，散布模板）按名字引用同目录 js 中 Page/Component 的方法（声明侧），双源零断言——JS 方法改名/删除→wxml 绑定运行时静默失效（点击无反应），小程序无 tsc 编译期零拦截；check-mp-structure.js 只挡四件套齐全/tabBar 注册，绑定名↔方法集是它的盲区。不变量（单向子集，F240/F243/F246 同向）：wxml 静态事件绑定名集 ⊆ 同目录 js 可用方法集（Page 取 Page({}) 顶层键；Component 取 methods 块键）；动态绑定（值含{{}}）计数不拦，缺输入/绑定集空/断言败均 exit 1（F212 不放行）；npm run check:wxml-handlers 接入 CI check job + Makefile check 链（wxml-handlers-check，委托单一源）；变异三档实证（scan.wxml 绑定改名 exit 1 精确拦 / station-card Component methods 改名 exit 1 精确拦 / mv 走 payment.js 缺输入 exit 1，sed 反向还原后基线 exit 0，F231 铁律）；守卫首跑即撞出两处真实死绑定并修复：favorites 空态"去发现站点"按钮 onGoHome 无方法体=死按钮（补 wx.switchTab 回首页）+ index 地图 bindupdated="onMapUpdated" 引用不存在方法（死绑定移除）；基线实测 14 wxml / 63 静态绑定全对账通过；eslint 0err/0warn + jest 230 绿复验
- 导航目标↔页面注册双源对账守卫（F246）：运行时 wx.navigateTo/redirectTo/switchTab/reLaunch 的 url 字面量（调用侧，散布各页面）与 app.json pages 数组（声明侧，唯一注册源）双源零断言，任一侧单独变更即漂移——页面改名/移除注册→跳转运行时 "navigateTo:fail page is not found"；tabBar 页用 navigateTo/redirectTo 或非 tabBar 页用 switchTab→运行时 fail（F243 探测集↔声明集同族）。不变量（单向子集，F240/F243 同向）：静态导航目标集 ⊆ 注册页集；switchTab 目标 ∈ tabBar 页集、navigateTo/redirectTo 目标 ∉ tabBar 页集（reLaunch 只查子集）；check-mp-structure.js 只挡注册四件套齐全/tabBar 引用已注册页，调用侧字面量是它的盲区。提取含模板字符串，query/插值截断取静态前缀，纯动态 url 计数不拦；缺输入/注册集空/目标集空/断言败均 exit 1（F212 不放行）；npm run check:nav-targets 接入 CI check job + Makefile check 链（nav-targets-check，委托单一源）；变异四档实证（app.json 移除 coupons 注册 exit 1 双调用点精确拦 / profile.js 跳转目标改名 exit 1 / mv 走 app.json 缺输入 exit 1 / switchTab→navigateTo 撞 tabBar 页 exit 1，sed 反向还原后基线 exit 0，F231/F238 铁律禁 git checkout）；接手花絮：并发轮脚本撞 eslint 4 errors（generator-star-spacing×2 + max-depth 嵌套5>4×2）→提取逻辑抽 helper 函数降深+星号位置修正，重构后基线+变异复验全中；eslint 0err/0warn + jest 230 绿复验；基线实测 18 个静态跳转目标 ⊆ 11 个注册页

### Added
- auth 存储键双源对账守卫（F240）：scripts/check-auth-keys.js — 'token'/'userInfo' 存储键名在 app.js（boot 恢复读侧）与 services/api.js（登录写入侧）双源硬编码字面量且零断言，任一侧整侧改名→ boot 恢复读旧键静默落空→用户持有有效 token 却被静默登出（F224 双源漂移同族；eslint 守卫 F214 只挡认证层外直读写，层内双源漂移不设防；app.js 无测试文件，往返路径零覆盖）。不变量：keys(app.js) ⊆ keys(api.js)，提取 wx.get/set/removeStorage(Sync) 首参字面量+异步对象形态 key 属性（与 F214 selector 双形态对齐）；npm run check:auth-keys 接入 CI check job + Makefile check 链（auth-keys-check，委托单一源）；变异三档实证（api.js 整侧 token 改名 exit 1 / app.js 整侧 userInfo 改名 exit 1 / api.js 缺输入 exit 1，sed 反向还原后基线 exit 0；F231/F238 铁律：变异还原禁 git checkout）；eslint 0err/0warn + jest 230 绿复验；花絮：首版变异档只改 api.js 单处未拦住——单边部分改名=文件内部自相矛盾（api.test.js 领地），整侧改名才是双源漂移语义，变异档设计须对齐守卫的真实漂移场景

### Added
- userInfo 本地访问器补齐 + globalData.userInfo 裸字段守卫扩展（F239）：token 侧有 app.getToken()（globalData+storage 兜底）而 userInfo 侧无同构访问器=同型半边缺口——冷启动 onLaunch 走 api.getUserInfo() 异步回填，请求未回/失败时 globalData.userInfo 为空，页面直读=空态。修法：app.js 补 app.getUserInfo()（与 getToken 同构：globalData || getStorageSync('userInfo')）；迁移全仓唯一直读点 pages/profile/profile.js（loadUserInfo）；eslint 守卫③ selector 由 property.name='token' 扩为 /^(token|userInfo)$/（与既有守卫同块声明，F214 flat config 教训）；前置核验迁移后 pages/components/utils 零违规、ignores 并集未变=零行为变化；变异探针实证（globalData.userInfo+token 双注入 exit 1 精确报错 / 清理后 exit 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 登录入口单一源架构守卫（F233）：no-restricted-syntax 新增 selector（wx.login 精确匹配 property.name）——登录必须走 app.login() 统一入口（token 落盘 setStorageSync+globalData 双写 + code 兑换 api.login），页面直调绕过统一落盘=半登录态漂移（F208/F214 架构守卫同族第⑤条）；与既有守卫**同块声明**（flat config 同 rule id 后块覆盖不合并）；摸底全仓仅 app.js:47 一处且 app.js 已在 ignores 并集内=零行为变化（F220 预防式门控：零违规先行）；变异三档实证（profile 页注入 wx.login exit 1 精确报错 / 清理后全仓 exit 0 / 基线 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 端点地址单一源架构守卫（F227）：no-restricted-syntax 新增 2 条 selector（Literal + TemplateElement 首段）——运行时代码禁硬编码 http(s) URL 字面量，端点地址仅允许在 config/index.js 声明（环境切换单一源，F224 双源漂移同族缺口）；与 F208/F214 守卫**同块声明**（flat config 同 rule id 后块覆盖不合并）；ignores 并集新增 config/**（权威源）+ 测试文件（jest 断言 config 值/样例 URL 为合法用途，前置核验对既有①②③守卫零行为变化）；scan.js 注释内 URL 不参与 AST 零误伤；变异三档实证（Literal 注入 exit 1 精确报错 / 模板字符串注入 exit 1 / 清理后全仓 exit 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 运行时日志守卫（F220）：小程序运行时代码（app.js/config/components/pages/services/utils）启用 no-console（allow: warn/error）——console.log/info/debug 残留污染微信开发者工具控制台且可能泄露订单/位置/充电会话等敏感字段；既有 catch 块 console.error 17 处实测放行；scripts/（CLI 合法输出）不在 files 内天然豁免 + 测试文件（jest/node 环境）显式豁免；变异三档实证（pages 注入 log+debug 全拦精确报错 / scripts 注入 log 零误伤 / 清理后全仓 exit 0）；eslint 0err/0warn + jest 230 绿复验
- eslint 架构守卫扩展（F214）：敏感凭据 storage 键（'token'/'userInfo'）仅认证层（app.js/services/api.js）可读写 + 禁直读 globalData.token 裸字段（须走 app.getToken()，含 storage 兜底逻辑）；3 条新 no-restricted-syntax selector（sync/async storage 形态 + MemberExpression 链）与 F208 守卫**同块声明**——flat config 同 rule id 后块覆盖前块不合并，分块声明前条会静默失效（调试实测，教训固化）；ignores 取豁免并集（app.js+api.js），前置核验两文件零违规、页面私有键（scanHistory/station_filter）零误伤；pages/profile 直读 globalData.token 改走 app.getToken()；变异测试实证（6 类违规注入全拦 exit 1 / F208 合并块回归仍触发 / 非敏感键零误伤 / 清理后 exit 0）；eslint 0err/0warn + jest 230 绿复验
- eslint 架构守卫（F208）：no-restricted-syntax 禁页面/组件直连 wx.request，HTTP 必须走 services/api.js 统一封装（防绕过 baseURL/token 注入/统一错误处理/401 登出）；AST 级精确匹配 property.name='request'，wx.requestPayment/wx.uploadFile 不误伤（grep 前缀匹配会误报——payment.js 的 wx.requestPayment 即实例，守卫用 AST 规避）；变异测试三档实证（注入违规 exit 1/清理后 exit 0/全仓复验 exit 0）；jest 230 绿复验

### Changed
- CI 健壮性补齐（F193/F199 模式例行体检落地本仓）：ci.yml 两 job 补 timeout-minutes（check=15 / structure=10，此前挂死最多吃满 GitHub 默认 6h runner）+ 新增 concurrency（cancel-in-progress，push/PR 并发跑批自动取消旧跑）；YAML 解析+结构断言校验（timeout/concurrency/原有 steps 全实测确认）；同轮摸底发现 jest 有 collectCoverageFrom 但无 coverageThreshold（覆盖率回退无声通过，F201 同型缺口），留测试维度轮按 F201 协议处理

### Added
- eslint 新增 78 条防回归规则（第六批，累计质量规则 63→141）：ESLint 核心规则全量扫描 — builtin 292 条去掉 recommended/已启用后 166 候选一次性临时入 config 实测，95 条 0 违规；剔除 7 条已废弃（no-catch-shadow / no-native-reassign / no-negated-in-lhs / no-new-symbol / no-spaced-func / lines-around-directive / id-blacklist）、9 条无选项即空转（no-restricted-* ×6 / id-denylist / id-match / jsx-quotes 无 JSX）、no-warning-comments（防 TODO 摩擦）、no-undefined（实测 34 违规），收 78 条：no-shadow / no-await-in-loop / complexity / max-depth / default-param-last / logical-assignment-operators / prefer-object-has-own / prefer-promise-reject-errors / semi / linebreak-style / unicode-bom 等；eslint exit 0 + jest 230 绿复验
- eslint 新增 20 条质量防回归规则（第五批）：no-labels / no-div-regex / accessor-pairs / no-nested-ternary / no-new-require / no-octal-escape / no-void / no-iterator / prefer-spread / prefer-rest-params / no-object-constructor / no-new-object / dot-notation / no-extend-native / no-return-await / symbol-description / no-duplicate-imports / no-useless-constructor / no-bitwise / no-param-reassign；候选池 24 条先全仓扫描实测（camelcase 46 / prefer-template 6 / no-confusing-arrow 3 违规剔除，no-with 与 recommended 重复剔除），0 违规 20 条全收。累计质量规则 43→63
- eslint 新增 11 条质量防回归规则（第二批）：no-implicit-coercion / no-empty-function / no-unneeded-ternary / no-lonely-if / prefer-object-spread / no-useless-computed-key / no-dupe-else-if / default-case / no-alert / no-multi-str / yoda；加入时全仓 0 违规（util.js padZero 隐式拼接顺手修复；notifications.js fire-and-forget catch 显式 disable+注释）
- eslint 新增 12 条质量防回归规则（第三批）：no-template-curly-in-string / no-unmodified-loop-condition / array-callback-return / no-useless-call / no-useless-concat / no-else-return / no-promise-executor-return / no-unsafe-optional-chaining / no-case-declarations / no-sequences / no-new-wrappers / prefer-regex-literals；加入时全仓 0 违规（测试文件 4 处 executor-return 顺手修为块体）。累计质量规则 19→31
- eslint 新增 12 条质量防回归规则（第四批）：no-throw-literal / no-irregular-whitespace / no-unreachable-loop / no-unused-expressions / require-await / no-multi-assign / no-extra-bind / no-useless-rename / no-array-constructor / prefer-numeric-literals / no-proto / no-new-func；加入时全仓 0 违规。累计质量规则 31→43
- eslint 启用 reportUnusedDisableDirectives=error：失效 disable 注释直接报错，防规则名笔误/规则删除后静默失效；加入时全仓 0 处失效
- CHANGELOG 清理：移除 Unreleased 段重复的第二批条目（F163 补回时误留的重复行）

### Changed
- lint 调用点单一源收敛（F195）：实测撞出 `npm run lint` 缺 `--max-warnings 0`（本地过 CI 红的门限漂移）→ package.json lint 补齐阈值，Makefile lint / scripts/lint-ci.js / CI ci.yml 三处全部委托 `npm run lint`（四处调用点归一）；变异测试实证门限有效（临时注入 no-var/no-unused-vars 违规 → exit 1 正确拦截，清理后 exit 0），lint:ci 全过 + jest 230 绿复验
- eslint 配置卫生去重（F189）：移除 22 条与 `js.configs.recommended` 完全重复的规则声明（no-undef / no-redeclare / no-dupe-keys / no-debugger / no-duplicate-case / no-prototype-builtins / no-self-assign / no-shadow-restricted-names / no-sparse-arrays / no-unreachable / no-useless-escape / no-misleading-character-class / no-async-promise-executor / no-class-assign / no-const-assign / no-this-before-super / require-yield / no-fallthrough / no-dupe-else-if / no-unsafe-optional-chaining / no-case-declarations / no-irregular-whitespace）；带选项覆盖的 no-unused-vars（argsIgnorePattern）/ no-constant-condition（checkLoops:false）保留；`--print-config` 前后逐条 diff = 零变化，eslint exit 0 + jest 230 绿 + lint:ci 全过复验

### Fixed
- `scan.wxml` 引用缺失的 `/assets/icons/scan-big.png` → 替换为 emoji 占位图标（F87）
- 6 处页面死链导航修复（F70：navigateBack/navigateTo 缺 fallback）

### 待办
- 真 appid 替换（当前占位符，待丁哥）
- 腾讯地图 MAP_KEY 配置
- 头像昵称 `<button open-type="chooseAvatar">` 采集方案
- api.js 错误路径分支覆盖补强（当前 branch 78.57%，实测 2026-08-04；旧记录 69.6% 已过期）
- scan-big.png 正式图标替换（当前 emoji 占位）

## [1.1.0] - 2026-07-31

### Added
- 部署门控脚本 `npm run deploy` / `deploy:check`（scripts/deploy.js）：结构门控→appid校验→密钥校验→miniprogram-ci 上传体验版，分级退出码（0/1/2/3），`--check` 干跑验证管线
- 部署脚本行为测试 ×3（门控先行 / appid占位拦截 / 参数校验），测试总数 215→218
- `.gitignore` 补 `private-key/`（代码上传密钥不落库）
- README 补「部署与发布」段 + 命令表

### 已知阻塞
- 真 appid + 上传密钥待丁哥；就位前 `deploy:check` 止步于 appid 校验（设计内拦截）

## [1.0.0] - 2026-07-31

### Fixed
- 上传包瘦身：`packOptions.ignore` 补 dir×2 + regexp×1 + file×3（lockfile 单项 160K），开发产物不再进微信上传包
- 移除 `app.js` 废弃 API `wx.getSystemInfoSync`（2.20.1+ 废弃，且零消费方）
- `profile.js` 移除废弃 API `wx.getUserProfile`（2.27.1+ 废弃，返回匿名"微信用户"会污染服务端资料），改静默登录
- 修复 jest 并行跑 worker 泄漏：cache TTL 真实定时器 suite 结束未清
- 移除误提交的 `coverage/` 产物，补 `.gitignore`

### Added
- ESLint 10 flat config 门控（`npm run lint`，0 错 0 警），修 20 处历史问题
- 小程序结构构建门控 `npm run check`：JSON 合法性 / 页面四件套 / tabBar 图标 / 组件引用解析
- 补齐 tabBar 缺失图标 ×8
- Jest 测试体系：8 套件 215 用例全绿，覆盖率 92.9%（services/utils/config）

### Changed
- B3 真 API 对齐：充电/订单/优惠券/积分全量接 `/business` 经营域
- 登录改 OAuth2 form-urlencoded；新增 snake→camel 归一化层（mapOrder/mapCoupon/mapPoints/mapPagination），UI 不再直碰后端字段
- 33 条契约测试锁定前后端字段映射

## [0.2.0] - 2026-07-02

### Changed
- API 配置对齐 `/api/v1/` 前缀

## [0.1.0] - 2026-06-23

### Added
- P1 首版：充电、支付、订单、地图、实时监控
