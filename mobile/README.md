# 天链运维 - 移动端 APP 打包说明

> **应用名称**: 天链运维  
> **技术栈**: Expo SDK 50 + React Native 0.73 + TypeScript  
> **当前版本**: 1.0.0  
> **包名**: `com.tianlian.v3`

---

## 📁 项目结构

```
mobile/
├── App.tsx                 # 应用入口，导航和Provider配置
├── app.json                # Expo 基础配置
├── app.config.js           # Expo 动态配置(环境变量/权限/更新)
├── eas.json                # EAS Build 配置
├── babel.config.js         # Babel 配置(路径别名)
├── package.json            # 依赖和脚本
├── tsconfig.json           # TypeScript 配置
├── build-android.sh        # Android APK 一键打包脚本
├── assets/                 # 图标和启动图资源
│   ├── icon.png            # 应用图标 (1024x1024)
│   ├── splash.png          # 启动屏图片
│   ├── adaptive-icon.png   # Android 自适应图标
│   └── favicon.png         # Web Favicon
└── src/
    ├── screens/            # 9个页面组件
    │   ├── LoginScreen.tsx          # 登录
    │   ├── HomeScreen.tsx           # 首页
    │   ├── DevicesScreen.tsx        # 设备列表(离线支持)
    │   ├── DeviceDetailScreen.tsx   # 设备详情(离线支持)
    │   ├── StationDetailScreen.tsx  # 站点详情(离线支持)
    │   ├── WorkOrdersScreen.tsx     # 工单列表
    │   ├── WorkOrderDetailScreen.tsx# 工单详情(离线支持)
    │   ├── EvaluationScreen.tsx     # 运维评价(离线支持)
    │   └── ProfileScreen.tsx       # 个人中心(离线支持)
    ├── services/
    │   ├── api.ts           # API 封装(axios 拦截器)
    │   ├── cache.ts         # 离线数据缓存(AsyncStorage)
    │   ├── sync.ts          # 数据同步(全量/增量)
    │   ├── conflict.ts      # 离线冲突检测与解决
    │   └── index.ts         # 服务导出
    ├── store/
    │   └── OfflineContext.tsx # 离线模式 Context Provider
    ├── hooks/
    │   └── useNetwork.ts   # 网络状态 Hook(NetInfo)
    └── components/
        └── NetworkStatus.tsx # 网络状态指示器
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd mobile
npm install
```

### 2. 启动开发服务器

```bash
npx expo start

# 或使用 npm script
npm start
```

启动后在终端按:
- `a` → Android 模拟器
- `i` → iOS 模拟器
- `w` → Web 浏览器
- `r` → 重新加载

### 3. 扫描 Expo Go 预览

用手机 Expo Go App 扫描终端输出的二维码即可预览。

---

## 📦 Android APK 打包

### 方式一: EAS Build（推荐 ⭐）

```bash
# 安装 EAS CLI
npm install -g eas-cli

# 登录 Expo 账号
eas login

# 打包 APK（生产环境）
./build-android.sh --eas --prod --apk

# 打包预览版 APK
./build-android.sh --eas --preview --apk

# 打包 AAB（用于 Google Play 上架）
./build-android.sh --eas --prod --aab
```

### 方式二: 本地打包

```bash
# 需要先安装 Android Studio 和 Android SDK

# 生成原生 Android 项目
npx expo prebuild --platform android

# 本地打包 APK
./build-android.sh --local --apk
```

### 方式三: Expo Classic Build

```bash
# 先登录 Expo
npx expo login

# 打包
npx expo build:android -t apk
```

---

## 🔑 Android 签名配置

### 生成签名密钥

```bash
# 使用脚本生成
./build-android.sh --keystore

# 或手动生成
keytool -genkey -v \
  -keystore android/app/tianlian.keystore \
  -alias tianlian \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

### 上传到 Expo（EAS Build 用）

```bash
# 上传 Keystore 到 Expo 云端
eas credentials

# 选择 Android → 上传现有 Keystore
```

---

## 🔧 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BUILD_TYPE` | 构建产物 (apk/aab) | `apk` |
| `BUILD_PROFILE` | 构建环境 (development/preview/production) | `production` |
| `APP_VERSION` | 应用版本号 | `1.0.0` |
| `BUILD_NUMBER` | 构建编号 | `1` |
| `APP_ENV` | 环境标识 (development/production) | `production` |

---

## 🌐 API 配置

开发环境 API 地址在 `src/services/api.ts` 中配置:

```typescript
const API_BASE_URL = 'http://192.168.1.102:8080/api/v1';
```

生产环境通过 `app.config.js` 中的 `extra.API_BASE_URL` 配置。

---

## 📱 功能总览

| 功能模块 | 状态 | 离线支持 | 说明 |
|---------|------|---------|------|
| **登录** | ✅ | ❌ | 用户名密码登录 |
| **首页仪表盘** | ✅ | ❌ | 设备统计/快速入口 |
| **设备管理** | ✅ | ✅ | 设备列表/在线状态 |
| **设备详情** | ✅ | ✅ | 健康度/维护记录/报修 |
| **站点详情** | ✅ | ✅ | 站点信息/设备分布/工单 |
| **工单管理** | ✅ | ❌ | 工单列表/状态筛选 |
| **工单详情** | ✅ | ✅ | 时间线/催单/验收 |
| **运维评价** | ✅ | ✅ | 团队评分/工程师评价 |
| **个人中心** | ✅ | ✅ | 资料修改/退出登录 |
| **离线模式** | ✅ | ✅ | 网络断开自动切换缓存 |
| **数据同步** | ✅ | ✅ | 网络恢复自动全量同步 |
| **冲突解决** | ✅ | ✅ | 离线操作冲突检测/合并 |
| **网络状态** | ✅ | ✅ | 实时状态条/同步提示 |

---

## 🧪 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | `admin123` |

---

## ❓ 常见问题

### Q: EAS Build 报错 "unauthorized"
**解决**: 运行 `eas login` 重新登录 Expo 账号

### Q: 本地打包找不到 Android SDK
**解决**: 安装 Android Studio，配置 `ANDROID_HOME` 或 `ANDROID_SDK_ROOT`

### Q: iOS 打包失败
**解决**: 需要在 macOS 上运行，且有 Apple Developer 账号

### Q: APK 安装后无法连接 API
**解决**: 
1. 检查手机与服务器在同一局域网
2. 确认 API 地址配置正确
3. Android 9+ 需要配置 `usesClearTextTraffic: true` (开发环境)

### Q: Metro bundler 启动报错
**解决**: 
```bash
# 清除缓存
npx expo start -c

# 或彻底清除
rm -rf node_modules && npm install
npx expo start -c
```

---

## 📊 构建历史

| 日期 | 版本 | 构建号 | 类型 | 方式 |
|------|------|--------|------|------|
| 2026-05-18 | 1.0.0 | 1 | APK | EAS Build |

---

## 🔗 相关链接

- [Expo 文档](https://docs.expo.dev/)
- [EAS Build 文档](https://docs.expo.dev/build/introduction/)
- [React Native 文档](https://reactnative.dev/)
- 项目: `projects/tianlian-v3/mobile/`

---

_最后更新: 2026-05-18_