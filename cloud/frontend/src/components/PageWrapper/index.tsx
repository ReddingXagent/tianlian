/**
 * PageWrapper - 通用页面包装器
 * 整合 Loading骨架屏 / Error错误边界 / Empty空状态 / PageTransition 过渡动画
 *
 * 用法:
 * <PageWrapper loading={loading} type="table" hasData={data.length > 0}>
 *   <Table ... />
 * </PageWrapper>
 */
import React from 'react';
import type { ReactNode } from 'react';
import { Result, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import SkeletonPage from '../Skeleton';
import EmptyState from '../EmptyState';
import PageTransition from '../PageTransition';

interface PageWrapperProps {
  children: ReactNode;
  /** 是否加载中 */
  loading?: boolean;
  /** 骨架屏类型 */
  skeletonType?: 'dashboard' | 'table' | 'card' | 'detail' | 'list';
  /** 骨架屏数量 */
  skeletonCount?: number;
  /** 是否无数据 */
  hasData?: boolean;
  /** 空状态配置 */
  empty?: {
    type?: 'default' | 'search' | 'device' | 'alarm' | 'order' | 'report';
    title?: string;
    description?: string;
    actionText?: string;
    onAction?: () => void;
  };
  /** 是否有错误 */
  error?: Error | string | null;
  /** 错误重试 */
  onRetry?: () => void;
  /** 页面过渡动画类型 */
  transition?: 'fade' | 'slide-up' | 'slide-left' | 'scale';
  /** 附加 className */
  className?: string;
}

const PageWrapper: React.FC<PageWrapperProps> = ({
  children,
  loading = false,
  skeletonType = 'table',
  skeletonCount = 5,
  hasData = true,
  empty,
  error,
  onRetry,
  transition = 'fade',
  className = '',
}) => {
  // 加载态：显示骨架屏
  if (loading) {
    return (
      <PageTransition effect={transition}>
        <SkeletonPage type={skeletonType} count={skeletonCount} />
      </PageTransition>
    );
  }

  // 错误态
  if (error) {
    return (
      <PageTransition effect={transition}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: 360,
            padding: 48,
          }}
        >
          <Result
            status="error"
            title="页面加载失败"
            subTitle={typeof error === 'string' ? error : error.message}
            extra={
              onRetry && (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={onRetry}
                >
                  重试
                </Button>
              )
            }
          />
        </div>
      </PageTransition>
    );
  }

  // 空态
  if (!hasData && empty) {
    return (
      <PageTransition effect={transition}>
        <EmptyState
          type={empty.type}
          title={empty.title}
          description={empty.description}
          actionText={empty.actionText}
          onAction={empty.onAction}
        />
      </PageTransition>
    );
  }

  // 正常渲染
  return (
    <PageTransition effect={transition} className={className}>
      {children}
    </PageTransition>
  );
};

export default PageWrapper;
