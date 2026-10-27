/**
 * PageHeader - 通用页面头部组件
 * 
 * Phase5 UI/UX优化: 统一所有页面的标题区样式
 * 支持: 标题、面包屑、操作按钮、描述、统计信息
 * 
 * 用法:
 * <PageHeader title="设备管理" onBack={() => navigate(-1)}>
 *   <Button type="primary">添加设备</Button>
 * </PageHeader>
 */
import React from 'react';
import type { ReactNode } from 'react';
import { Button, Breadcrumb, Row, Col, Space, Typography } from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title, Text } = Typography;

interface BreadcrumbItem {
  title: string;
  path?: string;
}

interface PageHeaderProps {
  /** 页面标题 */
  title: string;
  /** 标题前的图标 */
  icon?: ReactNode;
  /** 面包屑路径 */
  breadcrumb?: BreadcrumbItem[];
  /** 描述文字 */
  description?: string;
  /** 是否显示返回按钮 */
  onBack?: () => void;
  /** 返回按钮文字 */
  backText?: string;
  /** 是否显示刷新按钮 */
  showRefresh?: boolean;
  /** 刷新回调 */
  onRefresh?: () => void;
  /** 是否正在刷新 */
  refreshing?: boolean;
  /** 右上角操作区 */
  children?: ReactNode;
  /** 额外的统计信息 (显示在标题下方) */
  stats?: ReactNode;
  /** 底部边距 */
  gutterBottom?: number;
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 标签 (显示在标题后面) */
  tag?: ReactNode;
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  icon,
  breadcrumb,
  description,
  onBack,
  backText,
  showRefresh = false,
  onRefresh,
  refreshing = false,
  children,
  stats,
  gutterBottom = 24,
  style,
  tag,
}) => {
  const navigate = useNavigate();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  return (
    <div
      className="page-header"
      style={{
        marginBottom: gutterBottom,
        ...style,
      }}
    >
      {/* 面包屑 */}
      {breadcrumb && breadcrumb.length > 0 && (
        <Breadcrumb
          style={{ marginBottom: 8 }}
          items={breadcrumb.map(item => ({
            title: item.path ? (
              <a onClick={() => navigate(item.path!)} style={{ color: 'var(--text-secondary)', cursor: 'pointer' }}>
                {item.title}
              </a>
            ) : item.title,
          }))}
        />
      )}

      {/* 标题行 */}
      <Row
        align="middle"
        justify="space-between"
        style={{ flexWrap: 'wrap', gap: 8 }}
      >
        <Col flex="auto" style={{ minWidth: 200 }}>
          <Space align="center" wrap>
            {onBack !== undefined && (
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={handleBack}
                style={{ color: 'var(--text-secondary)' }}
              >
                {backText}
              </Button>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {icon && (
                <span style={{ fontSize: 22, color: 'var(--primary-color)' }}>{icon}</span>
              )}
              <Title
                level={4}
                style={{
                  margin: 0,
                  color: 'var(--text-primary)',
                  fontSize: 'clamp(18px, 2.5vw, 22px)',
                  fontWeight: 600,
                }}
              >
                {title}
              </Title>
              {tag}
            </div>
          </Space>
          {description && (
            <Text
              style={{
                color: 'var(--text-secondary)',
                fontSize: 13,
                marginTop: 4,
                display: 'block',
                marginLeft: onBack !== undefined ? 0 : 0,
              }}
            >
              {description}
            </Text>
          )}
        </Col>

        <Col
          flex="none"
          className="page-header-actions"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          {showRefresh && onRefresh && (
            <Button
              icon={<ReloadOutlined spin={refreshing} />}
              onClick={onRefresh}
              disabled={refreshing}
            >
              刷新
            </Button>
          )}
          {children}
        </Col>
      </Row>

      {/* 统计信息栏 */}
      {stats && (
        <div
          style={{
            marginTop: 12,
            padding: '12px 16px',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-color)',
          }}
        >
          {stats}
        </div>
      )}
    </div>
  );
};

export default PageHeader;

// Also export a Skeleton variant for when data is loading
export const PageHeaderSkeleton: React.FC<{ hasBack?: boolean; hasActions?: boolean }> = ({
  hasBack = false,
  hasActions = true,
}) => (
  <div style={{ marginBottom: 24 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {hasBack && <div className="skeleton-shimmer" style={{ width: 36, height: 36, borderRadius: 6 }} />}
        <div className="skeleton-shimmer" style={{ width: 160, height: 28, borderRadius: 6 }} />
      </div>
      {hasActions && (
        <div style={{ display: 'flex', gap: 8 }}>
          <div className="skeleton-shimmer" style={{ width: 80, height: 32, borderRadius: 6 }} />
          <div className="skeleton-shimmer" style={{ width: 100, height: 32, borderRadius: 6 }} />
        </div>
      )}
    </div>
  </div>
);