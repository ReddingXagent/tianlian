/**
 * types/modules/notification.ts — 通知相关类型
 */
export interface NotificationRule {
  id: number;
  name: string;
  event: string;
  channels: string[];
  recipients: string[];
  enabled: boolean;
  template: string;
  createdAt: string;
  updatedAt: string;
}

export interface NotificationRuleCreate {
  name: string;
  level: string;
  channels?: string[];
  receivers?: string[];
  enabled?: boolean;
}

export interface NotificationRuleUpdate {
  name?: string;
  level?: string;
  channels?: string[];
  receivers?: string[];
  enabled?: boolean;
}

export interface NotificationRuleCreated {
  id: number;
  name: string;
  level: string;
  channels: string[];
  receivers: string[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string | null;
}

// 通知模板 (Notification Template — from /notifications/templates)
export interface NotificationTemplate {
  id: number;
  name: string;
  channel: string;
  subject: string;
  body: string;
  variables: string[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

// 通知统计 (NotificationStats — from /notifications/stats)
export interface NotificationStats {
  totalTemplates: number;
  totalMessages: number;
  sentToday: number;
  failedCount: number;
  channelDistribution: Record<string, number>;
}

// 未读通知计数 (UnreadCount — from /notifications/unread-count)
export interface UnreadCount {
  unreadCount: number;
}

// 全部已读结果 (ReadAllResult — from POST /notifications/read-all)
export interface ReadAllResult {
  markedCount: number;
}

// 主动通知发送 (from POST /notifications/send)
export interface NotificationSendResult {
  status: string;
  channel: string | null;
  userId: string | null;
  title: string | null;
  sentAt: string | null;
}
