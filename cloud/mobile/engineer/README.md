# 天链工程师APP

天链运维平台工程师端移动应用，基于 React Native (Expo) 开发。

## 功能模块

### 1. 登录页
- 手机号验证码登录
- 账号密码登录
- 登录状态持久化

### 2. 工作台首页
- 今日工作统计（待接单数、进行中数、已完成数）
- 待接单工单列表（紧急程度、设备名、站点、派单时间、接单/转单按钮）
- 进行中工单列表（设备名、站点、到场状态、记录进度/完成按钮）

### 3. 工单详情
- 基本信息展示（工单编号、设备信息、站点信息、故障描述）
- 处理流程步骤展示（已接单→到场→处理中→已完成）
- 导航到站按钮（打开地图APP）
- 联系站长按钮（拨打电话）
- 开始处理（到场确认）
- 记录进度（文字描述、照片上传）
- 申请支援
- 申请备件
- 完成工单（故障原因、处理方案、更换配件、照片）

### 4. 知识库
- 故障案例列表
- 维修手册列表
- 搜索功能

### 5. 我的
- 个人资料（头像、姓名、工号、等级、手机）
- 工作统计（本月工单数、评分、平均响应时间）
- 消息通知
- 退出登录

## 技术栈

- **框架**: React Native (Expo)
- **语言**: TypeScript
- **导航**: React Navigation 6
- **网络**: Axios
- **存储**: AsyncStorage

## 项目结构

```
mobile/engineer/
├── App.tsx                  # 应用入口
├── src/
│   ├── screens/             # 页面组件
│   │   ├── LoginScreen.tsx
│   │   ├── WorkbenchScreen.tsx
│   │   ├── WorkOrderDetailScreen.tsx
│   │   ├── KnowledgeScreen.tsx
│   │   └── ProfileScreen.tsx
│   ├── navigation/          # 导航配置
│   │   └── AppNavigator.tsx
│   ├── services/            # API服务
│   │   └── api.ts
│   ├── types/               # 类型定义
│   │   └ index.ts
│   ├── components/          # 共享组件
│   └── hooks/               # 自定义Hooks
├── app.json                 # Expo配置
├── package.json             # 项目依赖
├── tsconfig.json            # TypeScript配置
└── babel.config.js          # Babel配置
```

## 安装与运行

### 安装依赖
```bash
npm install
```

### 启动开发
```bash
npm start
# 或
expo start
```

### 运行在iOS
```bash
npm run ios
```

### 运行在Android
```bash
npm run android
```

## API配置

API基础URL配置在 `src/services/api.ts`:
```typescript
const API_BASE_URL = 'http://demo.example.com/api/v1';
```

## 版本信息

- 版本号: 3.0.1
- 构建日期: 2026-05-15

---

天链运维平台 - 光储充智能运维管理