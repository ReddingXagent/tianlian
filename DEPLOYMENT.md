# 部署指南 (tianlian-station-app)

## 前置条件

- Node.js 20+ / npm
- Expo CLI (随 expo devDependencies 安装)
- EAS CLI (如需 OTA 或构建原生包): `npm i -g eas-cli`

## 环境变量

复制 `.env.example` → `.env`，填入实际值：

| 变量 | 说明 | 示例 |
|------|------|------|
| `EXPO_PUBLIC_API_URL` | 云端 API 地址 | `https://api.tianlian.example.com` |
| `EXPO_PUBLIC_API_PREFIX` | API 版本前缀 | `/api/v1` |

> ⚠️ 生产环境**必须 HTTPS**。HTTP 仅用于本地开发。

## 本地开发

```bash
npm install
npm start            # Expo Dev Server
npm run android      # 安卓模拟器/真机
npm run ios          # iOS 模拟器
```

## 构建检查

```bash
# 完整质量门控
make check           # tsc + eslint + jest

# 导出 bundle
make export          # android + ios

# 本地模拟 CI
make ci-local
```

## CI (GitHub Actions)

`.github/workflows/ci.yml` 两阶段流水线：

1. **check**: tsc → eslint → jest (coverage)
2. **export**: android bundle + ios bundle

push/PR → master 自动触发。

## EAS OTA 更新 (待配置)

需 Expo 账号和 EAS 项目：

```bash
eas login
eas update:configure
eas update --branch production --message "v1.0.0"
```

> 当前状态: 待丁哥提供 Expo 账号

## EAS 原生构建 (待配置)

```bash
eas build --platform android --profile production
eas build --platform ios --profile production
```

> 当前状态: 待丁哥提供 EAS 账号和密钥
