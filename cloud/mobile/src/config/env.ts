/**
 * 环境配置 — 出站点集中收口点 (卡 808e895d)
 *
 * 唯一允许引用 API 出站地址的模块：
 *   - dev:  局域网明文 HTTP（仅开发，usesClearTextTraffic 仅 dev 开启）
 *   - staging: 公网 IP 过渡环境
 *   - prod: 域名占位 https://youpengda.com（SSL 证书卡 c3722eba 待丁哥，落地后替换）
 *
 * 新增任何出站点（WebSocket / 上传 / 第三方）必须收敛到本文件，禁止散落字面量。
 */
import Constants from 'expo-constants';

type AppEnv = 'development' | 'staging' | 'production';

interface EnvConfig {
  appEnv: AppEnv;
  apiBaseUrl: string;
}

const ENV_URLS: Record<AppEnv, string> = {
  development: 'http://192.168.1.102:8080/api/v1',
  staging: 'http://demo.example.com/api/v1',
  // TODO(卡 c3722eba): 域名 SSL 落地后确认为最终地址
  production: 'https://youpengda.com/api/v1',
};

function resolveAppEnv(): AppEnv {
  const raw =
    (Constants.expoConfig?.extra as Record<string, unknown> | undefined)
      ?.APP_ENV;
  if (raw === 'development' || raw === 'staging' || raw === 'production') {
    return raw;
  }
  return 'production';
}

const appEnv = resolveAppEnv();

export const env: EnvConfig = {
  appEnv,
  apiBaseUrl:
    ENV_URLS[appEnv] ??
    ((Constants.expoConfig?.extra as Record<string, unknown> | undefined)
      ?.API_BASE_URL as string | undefined) ??
    ENV_URLS.production,
};

export const isDev = appEnv === 'development';
