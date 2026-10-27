/**
 * Expo App 动态配置
 * 天链运维 - 光储充智能运维管理平台
 * 
 * 此文件会与 app.json 合并，运行时动态生成最终的 Expo 配置。
 */

const IS_DEV = process.env.APP_ENV === 'development';
const APP_VERSION = '1.0.0';
const BUILD_NUMBER = process.env.BUILD_NUMBER || '1';

module.exports = {
  expo: {
    name: '天链运维',
    slug: 'tianlian-v3',
    version: APP_VERSION,
    orientation: 'portrait',
    icon: './assets/icon.png',
    userInterfaceStyle: 'light',
    scheme: 'tianlian',
    
    // Asset Bundling
    assetBundlePatterns: ['**/*'],

    // iOS 配置
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'com.tianlian.v3',
      buildNumber: BUILD_NUMBER,
      infoPlist: {
        NSCameraUsageDescription: '天链运维需要使用相机扫描设备二维码',
        NSPhotoLibraryUsageDescription: '天链运维需要访问相册上传设备照片',
        NSLocationWhenInUseUsageDescription: '天链运维需要获取位置信息用于站点定位',
      },
      config: {
        usesNonExemptEncryption: false,
      },
    },

    // Android 配置
    android: {
      package: 'com.tianlian.v3',
      versionCode: parseInt(BUILD_NUMBER, 10),
      
      // Adaptive Icon (Android 8.0+)
      adaptiveIcon: {
        foregroundImage: './assets/adaptive-icon.png',
        backgroundColor: '#1890ff',
      },

      // Android Manifest 权限
      permissions: [
        'INTERNET',
        'ACCESS_NETWORK_STATE',
        'ACCESS_WIFI_STATE',
        'CAMERA',
        'READ_EXTERNAL_STORAGE',
        'WRITE_EXTERNAL_STORAGE',
        'ACCESS_FINE_LOCATION',
        'ACCESS_COARSE_LOCATION',
        'VIBRATE',
      ],

      // Google Play 配置
      playStoreUrl: 'https://play.google.com/store/apps/details?id=com.tianlian.v3',

      // 允许使用明文HTTP (内网API)
      allowBackup: false,
    },

    // Web 配置
    web: {
      favicon: './assets/favicon.png',
      bundler: 'metro',
    },

    // Expo Updates (OTA 热更新)
    updates: {
      url: `https://u.expo.dev/tianlian-v3`,
      fallbackToCacheTimeout: 3000,
      checkAutomatically: 'ON_LOAD',
      enabled: !IS_DEV,
    },

    // EAS 配置
    extra: {
      eas: {
        projectId: 'tianlian-v3',
      },
      // 自定义环境变量 — 出站点 URL 统一由 src/config/env.ts 按档解析，此处仅传环境标识
      // dev: 局域网明文 HTTP；staging: 公网 IP 过渡；prod: 域名占位（SSL 卡 c3722eba）
      APP_ENV: process.env.APP_ENV || 'production',
    },

    // 插件 (仅 Expo config plugins，RN 包在 package.json 中声明)
    plugins: [
      'expo-status-bar',
      [
        'expo-splash-screen',
        {
          image: './assets/splash.png',
          imageWidth: 200,
          resizeMode: 'contain',
          backgroundColor: '#1890ff',
        },
      ],
      [
        'expo-build-properties',
        {
          android: {
            // 允许使用明文HTTP (仅 dev 内网API, 卡 808e895d)
            usesCleartextTraffic: IS_DEV,
          },
        },
      ],
    ],

    // Runtime 版本策略
    runtimeVersion: {
      policy: 'sdkVersion',
    },
  },
};