/**
 * types/modules/notification.ts — 通知类型
 */
import type { AlarmLevel } from './alarm';

export type NotificationType = 'alarm' | 'work_order' | 'system' | 'device' | 'revenue';

export interface AppNotification {
  id: number;
  type: NotificationType;
  title: string;
  message: string;
  level: AlarmLevel;
  sourceId?: number;
  sourceType?: string;
  isRead: boolean;
  createdAt: string;
  readAt?: string;
}
