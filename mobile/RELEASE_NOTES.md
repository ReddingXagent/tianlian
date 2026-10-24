# 天链移动端发布说明

## 发布信息

- **版本**: v3.0.0
- **发布日期**: 2026-04-03 11:55
- **平台**: Android
- **打包方式**: Expo Metro Bundler

## 构建产物

**输出目录**: `mobile/dist/`

```
dist/
├── _expo/
│   └── static/js/android/
│       └── AppEntry-*.hbc (1.75 MB)  # 主应用包
├── assets/                            # 静态资源
│   └── [6 个 PNG 图片文件]
└── metadata.json                      # 构建元数据
```

## 构建信息

- **打包工具**: Metro Bundler
- **打包时间**: 8812ms
- **包大小**: 1.75 MB (压缩后)
- **资源文件**: 6 个 PNG 图片

## 安装方式

### 方案 1: Expo Go (开发测试)
```bash
# 1. 安装 Expo Go APP
# 2. 扫描项目二维码
# 3. 自动加载应用
```

### 方案 2: 独立 APK (生产环境)
```bash
# 需要配置 EAS Build
npx eas build --platform android --profile production
```

### 方案 3: 本地测试
```bash
cd mobile
npx expo start
# 扫码或按 'a' 在 Android 模拟器运行
```

## 功能清单

### 已实现
- ✅ 用户登录/认证
- ✅ 首页仪表盘
- ✅ 设备列表/详情
- ✅ 站点管理
- ✅ 工单管理
- ✅ 告警管理
- ✅ 知识库浏览
- ✅ 扫码报修 (QR/PDF417)

### 待实现
- ⏳ 离线模式
- ⏳ 推送通知
- ⏳ 生物识别登录

## 技术栈

- **框架**: Expo SDK 52
- **UI**: React Native + NativeWind
- **导航**: React Navigation 7
- **状态管理**: React Context
- **网络**: Axios
- **相机**: expo-camera (扫码)

## 已知问题

1. 部分图标在 Android 上显示异常
2. 深色模式适配待完善
3. 离线缓存策略需优化

## 下一步计划

1. 配置 EAS Build 自动构建
2. 添加应用签名
3. 发布到应用商店
4. 实现离线模式

---

**构建者**: 大圣 🐵
**构建时间**: 2026-04-03 11:55:00
