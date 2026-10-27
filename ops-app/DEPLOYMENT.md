# 天链运维 App - 部署指南

## 前置条件

| 项目 | 要求 | 状态 |
|------|------|------|
| Expo 账号 | 需组织/个人 Expo 账号 | ⏳ 需部署方自备 (F25) |
| EAS CLI | `npm i -g eas-cli` | ⚠️ 本地未安装 |
| Android Keystore | EAS 自动管理或自备 | EAS 自动 |
| iOS Cert/Provisioning | EAS 自动管理或 Apple Developer 账号 | ⏳ 待 Apple Dev 账号 |
| app.json | slug/version/icons/plugins 齐全 | ✅ |
| eas.json | 3 profile (dev/preview/prod) | ✅ |
| .easignore | 排除测试/coverage/文档 | ✅ 本轮新增 |

## 构建配置概览

### eas.json 三档 Profile

| Profile | 用途 | 分发渠道 | 构建产物 |
|---------|------|----------|----------|
| development | 开发调试 | 内部 (distribution: internal) | development client APK/IPA |
| preview | 内测体验 | 内部 APK | 独立 APK，可直接安装 |
| production | 商店发布 | App Store / Google Play | AAB / IPA |

### app.json 关键配置

- **slug**: `tianlian-ops`
- **version**: `1.0.0`
- **Android package**: `com.tianlian.operator`
- **iOS bundleIdentifier**: `com.tianlian.operator`
- **scheme**: `tianlian-ops` (深度链接)
- **plugins**: `expo-secure-store`, `expo-asset`

## 部署步骤

### 1. 首次配置 (需 Expo 账号)

```bash
# 安装 EAS CLI
npm install -g eas-cli

# 登录 Expo 账号
eas login

# 关联项目 (首次)
eas init --id <your-project-id>
# 或创建新项目
eas init
```

### 2. 开发构建 (Development)

```bash
# Android 开发版 (development client)
eas build --profile development --platform android

# 安装到设备
eas build --profile development --platform android --auto-submit
```

### 3. 内测 APK (Preview)

```bash
# 生成可分享的 APK
eas build --profile preview --platform android

# 下载 APK 分发给测试人员
eas build:list --status finished
```

### 4. 生产构建 (Production)

```bash
# Android AAB (Google Play)
eas build --profile production --platform android

# iOS IPA (App Store)
eas build --profile production --platform ios

# 提交到商店
eas submit --profile production --platform android
eas submit --profile production --platform ios
```

### 5. OTA 更新 (Expo Updates)

```bash
# 配置 EAS Update (首次)
eas update:configure

# 推送 OTA 更新 (无需重新构建)
eas update --branch production --message "修复xxx"
```

## 本地验证 (无需 EAS)

以下验证可在本地完成，确认构建链路正常：

```bash
# TypeScript 编译检查
npx tsc --noEmit

# JS Bundle 导出 (Android)
npx expo export --platform android --output-dir /tmp/ops-export

# JS Bundle 导出 (iOS)
npx expo export --platform ios --output-dir /tmp/ops-export-ios

# 单元测试
npm test
```

## 已知部署缺口

| ID | 问题 | 影响 | 状态 |
|----|------|------|------|
| ~~F22~~ | ~~BASE_URL 硬编码生产 IP~~ | ~~已修复~~ | ✅ F130 已修复 (EXPO_PUBLIC_API_URL) |
| F25 | 无 Expo 账号，EAS 通道全不可用 | 无法云端构建/分发 | ⏳ 需部署方自备 |
| F89 | (user-mp) 生产 HTTP 非 HTTPS | 微信正式版强制 HTTPS | 📋 跨仓项 |
| — | 无 iOS Apple Developer 账号 | 无法 iOS 商店发布 | ⏳ 需自备账号 |

## 环境变量 (已实现 F130)

`src/services/api.ts` 使用 `EXPO_PUBLIC_API_URL` 环境变量，fallback 到生产 API：

```bash
# .env.example
EXPO_PUBLIC_API_URL=http://your-server-ip/api/v1

# 本地开发指向边缘网关
EXPO_PUBLIC_API_URL=http://192.168.31.10:8000/api/v1
```

### OTA 更新配置

app.json 已配置 `runtimeVersion.policy: sdkVersion` 和 `updates.url`，
关联 Expo 项目后即可推送 OTA：

```bash
eas update:configure  # 首次关联
eas update --branch production --message "修复xxx"
```

### Makefile 快捷命令

```bash
make help          # 显示所有命令
make check         # tsc + eslint + jest
make ci-local      # check + Android 导出 (模拟 CI)
make export-android # 仅导出 Android bundle
make export-ios     # 仅导出 iOS bundle
```

### GitHub Actions CI

`.github/workflows/ci.yml` 配置了 push/PR 触发的两阶段流水线：
1. **check**: tsc + eslint + jest (含 coverage)
2. **export**: Android + iOS bundle 导出验证

## 品牌资源

| 资源 | 规格 | 状态 |
|------|------|------|
| icon.png | 1024×1024 | ✅ 占位图 (蓝底白字 TL) |
| adaptive-icon.png | 1024×1024 | ✅ 占位图 |
| splash.png | 1242×2436 | ✅ 占位图 |
| favicon.png | 48×48 | ✅ 占位图 |

> 所有品牌资源为自动生成占位图，建议替换为正式设计稿。
