/**
 * types/modules/auth.ts — 认证相关类型
 */
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: import('./user').User;
}

/** POST /auth/refresh — 刷新令牌响应 */
export interface RefreshTokenResponse {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
}
