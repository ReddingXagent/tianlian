/**
 * 天链 V3 - Login 类型定义
 */
import type { UserType } from '../../utils/auth';

export type LoginMode = 'password' | 'sms';

// ======== 角色卡片配置 ========
export interface RoleCardConfig {
  type: UserType;
  title: string;
  subtitle: string;
  color: string;
  colorLight: string;
  gradient: string;
  icon: string; // emoji
  welcome: string;
}
