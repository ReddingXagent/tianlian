# Changelog

天链光储充运维系统 V3 的所有重要变更记录。

此文件由 `scripts/generate-changelog.py` 自动生成，基于 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

---

## [1.0.0] - 2026-05-18 — 🎉 正式版

### 🚀 Phase 8: 正式版发布

- **PostgreSQL 生产迁移**: SQLite → PostgreSQL 完整迁移脚本 + 连接池优化 (20+10)
- **Docker 多服务编排**: 后端+前端+PostgreSQL+Nginx 一键部署
- **Nginx 生产配置**: 统一入口(静态+API代理+WebSocket)+安全头+Gzip
- **全系统验收测试**: 66项自动化验收脚本 (89%通过率)
- **文档全面更新**: README v1.0 + PROJECT_STATUS + VERSION + CHANGELOG
- **移动端完整工程**: 站长APP(7页面)+工程师APP(5页面)双端
- **CI/CD 部署流水线**: 自动构建+部署+健康检查
- **Prometheus + Grafana 监控**: 指标采集+仪表盘可视化
- **SSL 证书自动化**: Let's Encrypt 配置脚本
- **安全加固**: CORS白名单 + 安全响应头 + 请求体大小限制 + 鉴权全覆盖
- **操作审计日志**: 全模块操作记录 + 登录/登出追踪
- **告警通知系统**: 实时消息推送 + 通知规则引擎
- **数据报表分析看板**: ECharts可视化 + Excel/CSV双格式导出
- **工单完整流程**: 创建→派单→处理→验收 + WebSocket实时推送
- **智能诊断系统**: 设备健康五维评估 + 故障码智能匹配 + AI日志分析

### 🐛 修复

- 模拟器测试修复(async)+24/24测试通过 (a994b8f5)
- API鉴权全覆盖: 3批次修复 (monitor/business/sensitive) (3e94eaa6, 45ea3c48, 6124e094)
- axios拦截器: 自动Token + 401跳转 (3aeba7b5)
- 侧边栏滚动/裁剪修复 (cbd31857, 20afa78d, fc2d072b)
- 前端白屏修复 (Config/Scan/Rbac/Telemetry) (e244ac99, cc77389f, f516ea53, ad8b76d1)
- 告警规则路由优先级修复 (5861abef)
- 遥测页面空数据保护 (ad8b76d1)
- 乱码修复: HTTP响应头charset=UTF-8 (0425095c)

---

## [Unreleased] - 2026-05-18


### 🚀 新功能

- 消息推送服务 - 告警自动通知 (20af9883)
- 通知规则配置 - 后端API+Config页面对接 (ca3e6e3d)
- CRUD审计日志注入(4模块12端点) (de66b45d)
- 侧边栏添加审计日志菜单项 (2a11e51a)
- 审计日志自动记录登录登出 (ddad99fc)
- 审计日志功能 - 用户操作全记录 (d048f832)
- 数据报表分析看板(echarts可视化) (541dde5e)
- 工单WebSocket实时推送 (90cc240c)
- 知识库富文本编辑器集成(react-quill-new) (8f228dc2)
- 告警通知中心 - 后端API+前端对接, 关联alarm表 (3918cb71)
- 天链V3自驱推进完成 (6526bf0d)
- 鉴权修复(3批)+安全加固(CORS+安全头+脱敏)+模拟器+测试+文档 (473c14db)
- 性能优化+安全加固+模拟器+文档 (930a0af2)
- 移动端适配 - AdminLayout修复+22页面padding统一+Dashboard响应式+CSS增强 (15ac688e)
- P0-告警规则配置 - 规则引擎+CRUD API+前端规则配置页 (7f97c079)
- 工程师APP开发完成 - 登录/工作台/工单详情/知识库/我的 (1994f13e)
- 站长APP新增页面 - 站点详情/设备详情/工单详情/评价/我的 (79e7bc3a)
- 工单完整流程 - 转单/催单/验收/驳回 + 前端操作按钮 (e59c51ec)
- AI智能日志分析系统 - 故障自动诊断流水线 (Phase 2) (7b464c95)
- 报表导出增加Excel格式支持 (xlsx) (29814460)
- 基于光储充协议的遥测数据+故障诊断系统 (e17cb725)
- Config系统配置功能细化 - 网关API调用 + 加载状态 (f0c9320f)
- AlarmNotices告警通知功能细化 - 添加加载状态 + 刷新按钮 + 预留API接口 (57f58dff)
- RemoteControl远程控制功能细化 - 真实API调用 + 设备列表加载 (186027c0)
- InspectionOps巡检运维功能细化 - 工单API调用 + 刷新按钮 + 待处理计数 (bfb533e4)
- Gateways网关管理功能细化 - 真实API调用 + SN码管理 + 固件管理 + 升级任务 (21cb93d9)
- Monitor动态监控功能细化 - 真实API调用 + 自动刷新(30s) + 在线设备统计 (ec1c5854)
- Stations站点管理功能细化 - 真实API调用 + 详情弹窗 + 增删改查 + 筛选搜索 + 统计卡片 (fe964a2f)
- Knowledge+Reports - 优化API调用+添加导出功能 (2026-04-29 13:33) (30ef93dd)
- Rbac权限管理 - 添加真实API调用 (2026-04-29 13:32) (f50057dc)
- Security安全管理 - 添加威胁详情弹窗+IP拉黑功能 (2026-04-29 13:31) (511a263f)
- Health状态监控 - 添加真实API调用 (2026-04-29 13:26) (b3815edb)
- Users用户管理 - 完善API调用+创建功能 (2026-04-29 13:25) (958615b4)
- Teams团队管理 - 完善API调用+创建功能 (2026-04-29 13:24) (250e2a27)
- 凌晨版本恢复 (2026-04-27 20:58) - AdminLayout/Config/InspectionOps (2aa2afd4)
- 添加Users用户管理页面 + Teams路由 + Config路由 + 后端users/teams API (26ed1825)
- 添加二维码打印菜单 + 标题映射补全 (ef7a5e16)
- 完善API路由 + 二维码打印页面 (424deebc)
- 天链V3核心功能补全 (16bfa39f)
- 打印排版优化 - 一页多张票据，节约纸张 (317c385b)

### 🐛 Bug 修复

- 模拟器测试修复(async)+operation_log路由注册, 24/24测试通过 (a994b8f5)
- 注册operation_log路由到api_router (24508220)
- diagnosis.py添加get_current_user导入 (37df1e4d)
- **auth**: 批量应用API鉴权到监控路由(第三批) (3e94eaa6)
- **auth**: 批量应用API鉴权到业务路由(第二批) (45ea3c48)
- **auth**: 批量应用API鉴权到敏感路由(第一批) (6124e094)
- **frontend**: axios拦截器 - 自动添加Authorization + 401自动跳转登录 (3aeba7b5)
- **auth**: API鉴权漏洞修复 - 添加get_current_user鉴权函数 + users路由强制验证 (a5ca1ead)
- 侧边栏展开账户管理子菜单后底部菜单被裁剪 + 底部图标不可点击 (fc2d072b)
- 告警规则路由优先级修复 + CI/CD部署流水线 + 数据库迁移 (5861abef)
- CI部署脚本 - pip走venv不激活环境 (5b0d9d88)
- 左侧菜单滚动修复 - Sider overflow:hidden + wrapper height:100vh (cbd31857)
- 侧边栏滚动修复 - 移除Sider styles属性+添加overflow覆盖 (2026-05-06) (20afa78d)
- 修复多个前端问题 - Scan重复导入 + Telemetry/FaultDiagnosis简化 (8aa153c2)
- 修复乱码问题 - 添加HTTP响应头charset=UTF-8 (0425095c)
- 遥测页面白屏修复 - 添加telemetry null检查+图表空数据处理 (ad8b76d1)
- 修复前端图标导入问题（使用通用图标替代） (7c7abb0d)
- Config页面白屏修复 - Table render函数签名修正 (_, record) (e244ac99)
- Config页面白屏修复 - antd v5 Tabs items API (e2192237)
- App.tsx添加ScanPage导入，修复ReferenceError (2026-04-29 14:02) (cc77389f)
- Rbac页面修复变量名冲突导致白屏 (2026-04-29 13:42) (f516ea53)
- 二维码打印页面适配云端API路径 (2096207a)
- 移除Web端扫码报修功能（APP端专用） (19eec295)

### ⚡ 性能优化

- 部署脚本添加数据库索引自动优化 (1d7809b3)

### 🔄 重构

- AdminLayout底部状态区布局调整 + 账户管理子菜单 (3ab78862)
- 对齐V3.0-2604281740版式 - AdminLayout/Dashboard版式确认一致 (08d6c4f2)

### 🧪 测试

- 前端单元测试完善(jest) (99868382)
- E2E测试 - Playwright核心流程 (01e16bea)
- 单元测试完善+文档补充 (76c085b7)

### 🔧 构建/工具

- gitignore cleanup - remove deploy artifacts (75815074)

### 📋 其他变更

- [天链] 移动端适配完成+云端修复+CI/CD+告警规则+GitNexus安装 (aa7d0e8d)
- [更新日志] 筑基10完成 + 创建新任务 (aa6192fc)
- [完成全部任务] 监控/优化/安全/测试/日志/备份/告警 (32f14e6d)
- 配置自驱动工作流 + 创建新任务 (dde7ebed)
- [完成全部任务] 云端测试/端点修复/性能优化/文档完善 (3980c710)
- [更新日志] 筑基8完成记录 (652396c4)
- [修复] 登录API调用格式 + 前端构建上传 (95ce9cfd)
- [更新日志] 筑基7完成记录 (43f7907c)
- [修复] 云端部署问题 + 新增security API (d8a3d634)
- 更新HEARTBEAT.md: 筑基5+筑基6完成记录 (5a0af295)
- [筑基6完成] 部署到云服务器 + 完整测试 (9e7e884f)
- [修复] Dashboard页面mock数据替换为真实API调用 (a2828997)
- [筑基6] 创建部署脚本和配置文件 (7c66fd68)
- [更新日志] 筑基5最终完成记录 (48d2b6b6)
- [修复] rbac.py和Dashboard页面改为真实API调用 (e0a3e5ff)
- [最终验证] 全部API和前端页面正常工作 (b495cbb6)
- [修复前端页面] 将mock数据替换为真实API调用 (aad24171)
- [更新日志] 筑基5续2完成记录 (d5c6ae30)
- [修复后端api] users和reports改为真实数据库查询 (b2a4a9df)
- 修复前端API调用与后端路由不匹配 (9a41f9d1)
- [筑基5续] 数据库schema对齐 + 枚举值修复 + vite proxy修复 (d7dde710)
- [筑基5] stations/teams/gateways API 改为真实数据库 + 枚举值修复 + 模型关系补齐 (23ffd945)
- [筑基5] 响应式适配 + 路由验证 + Mock数据 + Agent Skills集成 (08bfacae)
- [筑基4] Mock数据补齐 + Agent Skills 22个技能集成 (2cac753e)
- [后端api] alarms/workorders 返回dict格式 (2026-05-12) (66712f1d)
- [筑基3] Dashboard 悬浮面板点击跳转 (2026-05-12) (327d7e89)
- [筑基3] Security/Knowledge 页面增强 (2026-05-12) (0ad6e960)
- [筑基2] WorkOrders/InspectionOps 全面增强 (2026-05-12) (17a662cd)
- [筑基1] 布局/API/页面增强 (2026-05-12) (0d23958f)
- [备份] 2026-05-08 02:08 - 记忆/梦境/脚本更新 + cloud-provider-asr修复 + 新技能目录 (c5690657)
- V3.0-2605041844: Excel导出 + 菜单栏固定滚动 + 页面恢复 (aa08144b)
- V3.0-2505021635: AdminLayout侧边栏zIndex修复 + Dashboard悬浮面板x位置修正 + Reports页面重构 (5b66c91b)

---
## [v1.0-reimbursement] - 2026-04-22


### 🚀 新功能

- 票据整理归类 v1.0 - 自动分类、重命名、打印排版 (fe1f17dd)
- Monitor/Health API实现 + 部署测试完成 (f1fe35ef)
- 从tianlian-platform导入Monitor/Health/AlarmNotices/RemoteControl/Security/Rbac页面 + 完整菜单 (aab0ce94)
- 补全缺失页面 Teams/Users/Config/Map + 菜单路由 (825073ff)
- Gateways API + 前端网关管理页面 + 部署脚本 (d6232338)
- 移动端离线冲突解决机制 (3db385e6)
- 创建 Git Helper 技能 - 本地版本管理自动化 (8978b20f)
- 告警页面对接真实API (a3e28209)
- 监控页面对接真实API (fb81691e)
- 仪表盘页面对接真实API (2ac4e0cc)
- 设备管理页面对接真实API (96f7443f)
- multi-agent-cn 集成 Beads/Ontology 自动记录 (ed1eaffc)
- 创建 Beads/Ontology 集成脚本框架 (Task 2) (0e8e451e)

### 🧪 测试

- 添加方案 A 端到端集成测试 (bd-a1b2) (9688e293)

### 📚 文档

- 更新前端API对接进度 (4个页面) (6de55f9a)
- 更新API对接进度 (063e98ed)
- 更新开发进度 (f588889f)
- 添加方案 A 实施完成报告 (Task 6 完成) (826fe039)
- 添加方案 A 端到端验证报告 (workspace-oy2) (a23af6ca)
- 创建方案 A 使用指南 (Task 5 完成) (591bab89)
- 添加 Task 4 测试执行报告 (4447a0cb)
- 创建方案 A 实施计划 (bd-计划创建) (e9ee02b0)

### 📋 其他变更

- 环境验证 - 方案 A Task1 完成 (11d3a374)

---
## [v3.1.1] - 2026-04-20


### 🚀 新功能

- 更新前端功能 (7fb9e319)
- 更新前端功能 (b62fd350)
- 更新前端功能 (e431091c)

### 📚 文档

- 创建版本管理和需求文档体系 (4c61a62d)

---
## [v3.1.0] - 2026-04-19


### 🚀 新功能

- 消息推送服务 - 告警自动通知 (20af9883)
- 通知规则配置 - 后端API+Config页面对接 (ca3e6e3d)
- CRUD审计日志注入(4模块12端点) (de66b45d)
- 侧边栏添加审计日志菜单项 (2a11e51a)
- 审计日志自动记录登录登出 (ddad99fc)
- 审计日志功能 - 用户操作全记录 (d048f832)
- 数据报表分析看板(echarts可视化) (541dde5e)
- 工单WebSocket实时推送 (90cc240c)
- 知识库富文本编辑器集成(react-quill-new) (8f228dc2)
- 告警通知中心 - 后端API+前端对接, 关联alarm表 (3918cb71)
- 天链V3自驱推进完成 (6526bf0d)
- 鉴权修复(3批)+安全加固(CORS+安全头+脱敏)+模拟器+测试+文档 (473c14db)
- 性能优化+安全加固+模拟器+文档 (930a0af2)
- 移动端适配 - AdminLayout修复+22页面padding统一+Dashboard响应式+CSS增强 (15ac688e)
- P0-告警规则配置 - 规则引擎+CRUD API+前端规则配置页 (7f97c079)
- 工程师APP开发完成 - 登录/工作台/工单详情/知识库/我的 (1994f13e)
- 站长APP新增页面 - 站点详情/设备详情/工单详情/评价/我的 (79e7bc3a)
- 工单完整流程 - 转单/催单/验收/驳回 + 前端操作按钮 (e59c51ec)
- AI智能日志分析系统 - 故障自动诊断流水线 (Phase 2) (7b464c95)
- 报表导出增加Excel格式支持 (xlsx) (29814460)
- 基于光储充协议的遥测数据+故障诊断系统 (e17cb725)
- Config系统配置功能细化 - 网关API调用 + 加载状态 (f0c9320f)
- AlarmNotices告警通知功能细化 - 添加加载状态 + 刷新按钮 + 预留API接口 (57f58dff)
- RemoteControl远程控制功能细化 - 真实API调用 + 设备列表加载 (186027c0)
- InspectionOps巡检运维功能细化 - 工单API调用 + 刷新按钮 + 待处理计数 (bfb533e4)
- Gateways网关管理功能细化 - 真实API调用 + SN码管理 + 固件管理 + 升级任务 (21cb93d9)
- Monitor动态监控功能细化 - 真实API调用 + 自动刷新(30s) + 在线设备统计 (ec1c5854)
- Stations站点管理功能细化 - 真实API调用 + 详情弹窗 + 增删改查 + 筛选搜索 + 统计卡片 (fe964a2f)
- Knowledge+Reports - 优化API调用+添加导出功能 (2026-04-29 13:33) (30ef93dd)
- Rbac权限管理 - 添加真实API调用 (2026-04-29 13:32) (f50057dc)
- Security安全管理 - 添加威胁详情弹窗+IP拉黑功能 (2026-04-29 13:31) (511a263f)
- Health状态监控 - 添加真实API调用 (2026-04-29 13:26) (b3815edb)
- Users用户管理 - 完善API调用+创建功能 (2026-04-29 13:25) (958615b4)
- Teams团队管理 - 完善API调用+创建功能 (2026-04-29 13:24) (250e2a27)
- 凌晨版本恢复 (2026-04-27 20:58) - AdminLayout/Config/InspectionOps (2aa2afd4)
- 添加Users用户管理页面 + Teams路由 + Config路由 + 后端users/teams API (26ed1825)
- 添加二维码打印菜单 + 标题映射补全 (ef7a5e16)
- 完善API路由 + 二维码打印页面 (424deebc)
- 天链V3核心功能补全 (16bfa39f)
- 打印排版优化 - 一页多张票据，节约纸张 (317c385b)
- 票据整理归类 v1.0 - 自动分类、重命名、打印排版 (fe1f17dd)
- Monitor/Health API实现 + 部署测试完成 (f1fe35ef)
- 从tianlian-platform导入Monitor/Health/AlarmNotices/RemoteControl/Security/Rbac页面 + 完整菜单 (aab0ce94)
- 补全缺失页面 Teams/Users/Config/Map + 菜单路由 (825073ff)
- Gateways API + 前端网关管理页面 + 部署脚本 (d6232338)
- 移动端离线冲突解决机制 (3db385e6)
- 创建 Git Helper 技能 - 本地版本管理自动化 (8978b20f)
- 告警页面对接真实API (a3e28209)
- 监控页面对接真实API (fb81691e)
- 仪表盘页面对接真实API (2ac4e0cc)
- 设备管理页面对接真实API (96f7443f)
- multi-agent-cn 集成 Beads/Ontology 自动记录 (ed1eaffc)
- 创建 Beads/Ontology 集成脚本框架 (Task 2) (0e8e451e)

### 🐛 Bug 修复

- 模拟器测试修复(async)+operation_log路由注册, 24/24测试通过 (a994b8f5)
- 注册operation_log路由到api_router (24508220)
- diagnosis.py添加get_current_user导入 (37df1e4d)
- **auth**: 批量应用API鉴权到监控路由(第三批) (3e94eaa6)
- **auth**: 批量应用API鉴权到业务路由(第二批) (45ea3c48)
- **auth**: 批量应用API鉴权到敏感路由(第一批) (6124e094)
- **frontend**: axios拦截器 - 自动添加Authorization + 401自动跳转登录 (3aeba7b5)
- **auth**: API鉴权漏洞修复 - 添加get_current_user鉴权函数 + users路由强制验证 (a5ca1ead)
- 侧边栏展开账户管理子菜单后底部菜单被裁剪 + 底部图标不可点击 (fc2d072b)
- 告警规则路由优先级修复 + CI/CD部署流水线 + 数据库迁移 (5861abef)
- CI部署脚本 - pip走venv不激活环境 (5b0d9d88)
- 左侧菜单滚动修复 - Sider overflow:hidden + wrapper height:100vh (cbd31857)
- 侧边栏滚动修复 - 移除Sider styles属性+添加overflow覆盖 (2026-05-06) (20afa78d)
- 修复多个前端问题 - Scan重复导入 + Telemetry/FaultDiagnosis简化 (8aa153c2)
- 修复乱码问题 - 添加HTTP响应头charset=UTF-8 (0425095c)
- 遥测页面白屏修复 - 添加telemetry null检查+图表空数据处理 (ad8b76d1)
- 修复前端图标导入问题（使用通用图标替代） (7c7abb0d)
- Config页面白屏修复 - Table render函数签名修正 (_, record) (e244ac99)
- Config页面白屏修复 - antd v5 Tabs items API (e2192237)
- App.tsx添加ScanPage导入，修复ReferenceError (2026-04-29 14:02) (cc77389f)
- Rbac页面修复变量名冲突导致白屏 (2026-04-29 13:42) (f516ea53)
- 二维码打印页面适配云端API路径 (2096207a)
- 移除Web端扫码报修功能（APP端专用） (19eec295)

### ⚡ 性能优化

- 部署脚本添加数据库索引自动优化 (1d7809b3)

### 🔄 重构

- AdminLayout底部状态区布局调整 + 账户管理子菜单 (3ab78862)
- 对齐V3.0-2604281740版式 - AdminLayout/Dashboard版式确认一致 (08d6c4f2)

### 🧪 测试

- 前端单元测试完善(jest) (99868382)
- E2E测试 - Playwright核心流程 (01e16bea)
- 单元测试完善+文档补充 (76c085b7)
- 添加方案 A 端到端集成测试 (bd-a1b2) (9688e293)

### 📚 文档

- 更新前端API对接进度 (4个页面) (6de55f9a)
- 更新API对接进度 (063e98ed)
- 更新开发进度 (f588889f)
- 添加方案 A 实施完成报告 (Task 6 完成) (826fe039)
- 添加方案 A 端到端验证报告 (workspace-oy2) (a23af6ca)
- 创建方案 A 使用指南 (Task 5 完成) (591bab89)
- 添加 Task 4 测试执行报告 (4447a0cb)
- 创建方案 A 实施计划 (bd-计划创建) (e9ee02b0)

### 🔧 构建/工具

- gitignore cleanup - remove deploy artifacts (75815074)

### 📋 其他变更

- [天链] 移动端适配完成+云端修复+CI/CD+告警规则+GitNexus安装 (aa7d0e8d)
- [更新日志] 筑基10完成 + 创建新任务 (aa6192fc)
- [完成全部任务] 监控/优化/安全/测试/日志/备份/告警 (32f14e6d)
- 配置自驱动工作流 + 创建新任务 (dde7ebed)
- [完成全部任务] 云端测试/端点修复/性能优化/文档完善 (3980c710)
- [更新日志] 筑基8完成记录 (652396c4)
- [修复] 登录API调用格式 + 前端构建上传 (95ce9cfd)
- [更新日志] 筑基7完成记录 (43f7907c)
- [修复] 云端部署问题 + 新增security API (d8a3d634)
- 更新HEARTBEAT.md: 筑基5+筑基6完成记录 (5a0af295)
- [筑基6完成] 部署到云服务器 + 完整测试 (9e7e884f)
- [修复] Dashboard页面mock数据替换为真实API调用 (a2828997)
- [筑基6] 创建部署脚本和配置文件 (7c66fd68)
- [更新日志] 筑基5最终完成记录 (48d2b6b6)
- [修复] rbac.py和Dashboard页面改为真实API调用 (e0a3e5ff)
- [最终验证] 全部API和前端页面正常工作 (b495cbb6)
- [修复前端页面] 将mock数据替换为真实API调用 (aad24171)
- [更新日志] 筑基5续2完成记录 (d5c6ae30)
- [修复后端api] users和reports改为真实数据库查询 (b2a4a9df)
- 修复前端API调用与后端路由不匹配 (9a41f9d1)
- [筑基5续] 数据库schema对齐 + 枚举值修复 + vite proxy修复 (d7dde710)
- [筑基5] stations/teams/gateways API 改为真实数据库 + 枚举值修复 + 模型关系补齐 (23ffd945)
- [筑基5] 响应式适配 + 路由验证 + Mock数据 + Agent Skills集成 (08bfacae)
- [筑基4] Mock数据补齐 + Agent Skills 22个技能集成 (2cac753e)
- [后端api] alarms/workorders 返回dict格式 (2026-05-12) (66712f1d)
- [筑基3] Dashboard 悬浮面板点击跳转 (2026-05-12) (327d7e89)
- [筑基3] Security/Knowledge 页面增强 (2026-05-12) (0ad6e960)
- [筑基2] WorkOrders/InspectionOps 全面增强 (2026-05-12) (17a662cd)
- [筑基1] 布局/API/页面增强 (2026-05-12) (0d23958f)
- [备份] 2026-05-08 02:08 - 记忆/梦境/脚本更新 + cloud-provider-asr修复 + 新技能目录 (c5690657)
- V3.0-2605041844: Excel导出 + 菜单栏固定滚动 + 页面恢复 (aa08144b)
- V3.0-2505021635: AdminLayout侧边栏zIndex修复 + Dashboard悬浮面板x位置修正 + Reports页面重构 (5b66c91b)
- 环境验证 - 方案 A Task1 完成 (11d3a374)

---
## [初始版本] - 2026-04-19


### 📋 其他变更

- 恢复丢失的 7 个核心页面：AlarmNotices, Health, Map, Monitor, Rbac, RemoteControl, Security (36ee893d)
- Initial commit - tianlian-v3 current state (9749965f)

---

## [3.0.0] - 2026-06-14 — 🔧 健康监控 + 阈值配置化

### 🚀 Phase36: 用户体验提升 + 健康监控重构

- **T1: 移动端响应式适配** — 前端全局响应式布局改造
- **T2: 健康阈值配置化** — 7种设备类型差异化温度阈值，可DB配置+CRUD API
  - 新增 `HealthThresholdConfig` 模型
  - health_scorer 集成DB阈值配置（带缓存）
  - CRUD API: 列表/查询/更新/重置/批量初始化
  - 差异化默认值: 电池60°C最严 / 光伏85°C最宽松
- **T3: RBAC权限细化** — 角色管理 + API端点权限 + Tenants页面改造
- **T4: i18n国际化** — 中英文双语 + 日期/时区本地化

### 🚀 Phase37: 前端阈值管理页面

- Config页面新增「阈值配置」Tab
- 表格展示7种设备类型的温度/电气/漏电流阈值
- 编辑弹窗可修改所有阈值参数
- 支持重置为出厂默认值 + 批量初始化

### 🔧 运维修复

- nginx `/api/health` → `/api/v1/health` 302重定向
- 云端systemd后端服务修复（Python路径修正）
- 云端前端权限修复（chown www-data）
- 最新stable-v3.0代码部署上线

### 🛠 Phase37 收尾：测试门禁恢复 + 移动端编译 + 文档同步（2026-06-15）

- **后端 722 errors 根因修复**：conftest 重构（commit 99bc5aac）误删 `test_db` fixture，致 49 个测试文件、722 个用例 setup 失败
  - 补回 `test_db` fixture：session 级 schema 模板 + 函数级复制，兼顾隔离与性能
  - override 模块级 `SessionLocal`，服务层测试完全隔离
  - 成效：errors 722→60，passed 405→955
- **测试环境依赖补齐**：`requirements.txt` 漏列 pytz/numpy/pandas/openpyxl/qrcode/scikit-learn/joblib/httpx-ws 等运行时依赖
- **移动端编译修复**：缺失 `babel-plugin-module-resolver` 致 `expo export` 失败，补回 `@/*` 路径别名支持（主 APP 编译通过）
- **文档同步**：PROJECT_STATUS 更新至 Phase37，USER_MANUAL 补充设备类型温度阈值表
- **已知测试债**：errors 修复后暴露的「测试与 app 代码大面积不同步」，单独立项 Phase38（详见下条，errors 已进一步清零）

### 🛠 Phase37 续：errors 60→0 + 移动端 tsc 0 错误（2026-06-15）

- **后端 errors 60→0**：修复 3 类 setup 根因（commit f26331e5）
  - conftest `seed_stations`：`status="active"` → `StationStatus.NORMAL`（enum 重构为 NORMAL/MAINTENANCE/CLOSED 不接受 active，致 test_alarms/devices/rbac 等 20 个 LookupError）
  - 9 个测试文件登录密码 `"***"` → `admin123`（批量脱敏误伤，致 test_api_key/digital_twin 等 35 个登录 401）
  - conftest 新增 `async_client` fixture（httpx.ASGITransport，修 test_im_notify 用未定义 fixture 的 5 个 not found）
  - 成效：errors 60→0（passed 955→971；failed 148→173 为 errors 修复后暴露的断言债）
- **移动端 tsc --noEmit 0 错误**（commit 1c724025）：13 errors → 0
  - tsconfig exclude `engineer/`（独立 Expo 子项目，自带 tsconfig，被主 tsconfig 误纳入检查）
  - App.tsx 定义 `RootStackParamList` 泛型修复导航 route 类型
  - DeviceDetailScreen navigation 类型化，去掉 `as never` 与无效嵌套导航
- **测试债边界明确**：剩余 173 failed 为断言级「测试与 app 不同步」，Phase38 立项逐模块对齐
