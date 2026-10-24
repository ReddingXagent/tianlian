# 天链 V3 移动端打包指南

## 当前状态
- ✅ Expo框架已完成
- ✅ iOS原生项目已构建
- ✅ OfflineContext离线模式实现
- ⏳ 打包发布待配置

## Expo配置（app.json）

```json
{
  "expo": {
    "name": "天链光储充运维",
    "slug": "tianlian-v3",
    "version": "3.0.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "userInterfaceStyle": "light",
    "splash": {
      "image": "./assets/splash.png",
      "resizeMode": "contain",
      "backgroundColor": "#ffffff"
    },
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "com.tianlian.v3"
    },
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#ffffff"
      },
      "package": "com.tianlian.v3"
    },
    "web": {
      "favicon": "./assets/favicon.png"
    }
  }
}
```

## 打包方式

### 1. Expo云端打包（推荐）
```bash
cd mobile
npx expo login
npx expo build:ios --type archive  # iOS打包
npx expo build:android --type apk  # Android打包
```

### 2. 本地打包（iOS）
```bash
cd mobile/ios
pod install
# 使用Xcode打开 app.xcworkspace 打包
```

### 3. EAS Build（最新方式）
```bash
npx eas-cli build --platform ios
npx eas-cli build --platform android
```

## 打包前检查

### 1. 依赖完整性
```bash
cd mobile
npm install
```

### 2. iOS证书配置
- 需Apple Developer账号
- 配置bundleIdentifier
- 导入证书到Xcode

### 3. Android签名配置
- 生成keystore文件
- 配置gradle签名

## 功能列表

| 功能 | 状态 | 备注 |
|------|------|------|
| 登录 | ✅ | LoginScreen.tsx |
| 主页 | ✅ | HomeScreen.tsx |
| 设备管理 | ✅ | DevicesScreen.tsx |
| 站点详情 | ✅ | StationDetailScreen.tsx |
| 工单管理 | ✅ | WorkOrdersScreen.tsx |
| 知识库 | ✅ | KnowledgeScreen.tsx（engineer） |
| 离线模式 | ✅ | OfflineContext.tsx |

## 测试

### 启动模拟器
```bash
npx expo start
# 按 i 启动iOS模拟器
# 按 a 启动Android模拟器
```

### 测试账号
- 用户名: admin
- 密码: admin123

## 发布

### Expo发布
```bash
npx expo publish
# 用户通过链接下载: https://expo.io/@username/tianlian-v3
```

### App Store发布（iOS）
1. Xcode打包 → 生成.ipa文件
2. App Store Connect上传
3. 等待审核

### Google Play发布（Android）
1. Expo生成.aab文件
2. Google Play Console上传
3. 等待审核

## 常见问题

### Q: iOS打包失败
**原因**: 证书未配置或过期
**解决**: Apple Developer重新生成证书

### Q: Android打包失败
**原因**: keystore未配置
**解决**: `keytool -genkey -v -keystore tianlian.keystore`

### Q: 模拟器启动失败
**原因**: 依赖未安装
**解决**: `npm install` + `pod install`

---

**更新时间**: 2026-05-17
**当前版本**: 3.0.0
**打包状态**: ⏳ 待配置证书和签名