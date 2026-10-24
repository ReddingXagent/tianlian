/**
 * 空状态组件 - 列表/表格无数据时展示引导性空态
 * 支持自定义图标、标题、描述和操作按钮
 */
import React from 'react';
import { Empty, Button } from 'antd';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** 图标类型 */
  type?: 'default' | 'search' | 'device' | 'alarm' | 'order' | 'report';
  /** 自定义图标 */
  icon?: ReactNode;
  /** 主标题 */
  title?: string;
  /** 描述文案 */
  description?: string;
  /** 操作按钮文案 */
  actionText?: string;
  /** 操作按钮回调 */
  onAction?: () => void;
  /** 次要操作按钮 */
  secondaryActionText?: string;
  onSecondaryAction?: () => void;
  /** 是否显示 Image (默认 true) */
  showImage?: boolean;
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 子元素 (放在按钮下方) */
  children?: ReactNode;
}

/** 各类型默认文案 */
const DEFAULT_CONFIG: Record<string, { title: string; description: string }> = {
  default: {
    title: '暂无数据',
    description: '当前没有可显示的数据内容',
  },
  search: {
    title: '未找到匹配结果',
    description: '请检查搜索条件，或尝试使用其他关键词',
  },
  device: {
    title: '暂无设备',
    description: '尚未添加任何设备，请先接入设备或导入设备配置',
  },
  alarm: {
    title: '暂无告警',
    description: '当前系统运行正常，没有活跃的告警信息',
  },
  order: {
    title: '暂无工单',
    description: '当前没有待处理的工单任务',
  },
  report: {
    title: '暂无报表',
    description: '尚未生成任何报表，可以创建新的数据分析报表',
  },
};

const EmptyState: React.FC<EmptyStateProps> = ({
  type = 'default',
  icon,
  title,
  description,
  actionText,
  onAction,
  secondaryActionText,
  onSecondaryAction,
  showImage = true,
  style,
  children,
}) => {
  const config = DEFAULT_CONFIG[type] || DEFAULT_CONFIG.default;

  const builtInImageMap: Record<string, React.ReactNode> = {
    search: Empty.PRESENTED_IMAGE_SIMPLE,
    default: Empty.PRESENTED_IMAGE_DEFAULT,
  };

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: 360,
        padding: 48,
        ...style,
      }}
    >
      <Empty
        image={icon || (showImage ? builtInImageMap[type] || Empty.PRESENTED_IMAGE_DEFAULT : null)}
        description={
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
              {title || config.title}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', maxWidth: 360, margin: '0 auto' }}>
              {description || config.description}
            </div>
          </div>
        }
      >
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
          {secondaryActionText && onSecondaryAction && (
            <Button onClick={onSecondaryAction}>{secondaryActionText}</Button>
          )}
          {actionText && onAction && (
            <Button type="primary" onClick={onAction}>{actionText}</Button>
          )}
        </div>
        {children && <div style={{ marginTop: 16 }}>{children}</div>}
      </Empty>
    </div>
  );
};

export default EmptyState;
