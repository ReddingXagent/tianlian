/**
 * PageWrapper 组件测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PageWrapper from '../PageWrapper';

describe('PageWrapper', () => {
  describe('loading state', () => {
    it('should render skeleton when loading', () => {
      const { container } = render(
        <PageWrapper loading skeletonType="table" skeletonCount={3}>
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      // Skeleton should be visible
      expect(container.querySelector('.ant-skeleton')).toBeInTheDocument();
      // Content should NOT be visible
      expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    });

    it('should render different skeleton types', () => {
      const types = ['dashboard', 'table', 'card', 'detail', 'list'] as const;
      for (const type of types) {
        const { container, unmount } = render(
          <PageWrapper loading skeletonType={type} skeletonCount={1}>
            <div>Content</div>
          </PageWrapper>
        );
        expect(container.querySelector('.ant-skeleton')).toBeInTheDocument();
        unmount();
      }
    });
  });

  describe('error state', () => {
    it('should render error result when error is a string', () => {
      render(
        <PageWrapper error="网络连接失败">
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      expect(screen.getByText('页面加载失败')).toBeInTheDocument();
      expect(screen.getByText('网络连接失败')).toBeInTheDocument();
      expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    });

    it('should render error result when error is Error object', () => {
      const error = new Error('Something went wrong');
      render(
        <PageWrapper error={error}>
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      expect(screen.getByText('页面加载失败')).toBeInTheDocument();
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should show retry button when onRetry is provided', () => {
      const onRetry = vi.fn();
      render(
        <PageWrapper error="加载失败" onRetry={onRetry}>
          <div>Content</div>
        </PageWrapper>
      );
      const retryBtn = screen.getByText('重试');
      expect(retryBtn).toBeInTheDocument();
      fireEvent.click(retryBtn);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('should not show retry button when onRetry is not provided', () => {
      render(
        <PageWrapper error="加载失败">
          <div>Content</div>
        </PageWrapper>
      );
      expect(screen.queryByText('重试')).not.toBeInTheDocument();
    });
  });

  describe('empty state', () => {
    it('should render EmptyState when hasData is false and empty config provided', () => {
      render(
        <PageWrapper
          hasData={false}
          empty={{
            type: 'device',
            title: '暂无设备',
            description: '请添加第一个设备',
          }}
        >
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      expect(screen.getByText('暂无设备')).toBeInTheDocument();
      expect(screen.getByText('请添加第一个设备')).toBeInTheDocument();
      expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    });

    it('should show action button when empty.actionText is provided', () => {
      const onAction = vi.fn();
      render(
        <PageWrapper
          hasData={false}
          empty={{
            title: '暂无数据',
            actionText: '添加设备',
            onAction,
          }}
        >
          <div>Content</div>
        </PageWrapper>
      );
      const actionBtn = screen.getByText('添加设备');
      expect(actionBtn).toBeInTheDocument();
      fireEvent.click(actionBtn);
      expect(onAction).toHaveBeenCalledTimes(1);
    });
  });

  describe('normal state', () => {
    it('should render children when not loading, no error, and hasData', () => {
      render(
        <PageWrapper>
          <div data-testid="content">Hello World</div>
        </PageWrapper>
      );
      expect(screen.getByTestId('content')).toBeInTheDocument();
      expect(screen.getByText('Hello World')).toBeInTheDocument();
    });

    it('should render children when hasData is true and empty config is provided', () => {
      render(
        <PageWrapper
          hasData
          empty={{ title: 'No items', actionText: 'Add' }}
        >
          <div data-testid="content">Has Data</div>
        </PageWrapper>
      );
      expect(screen.getByTestId('content')).toBeInTheDocument();
    });
  });

  describe('priority', () => {
    it('should prioritize loading over error', () => {
      render(
        <PageWrapper loading error="Some error">
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      // Loading skeleton should appear, not error
      expect(screen.queryByTestId('content')).not.toBeInTheDocument();
      expect(screen.queryByText('页面加载失败')).not.toBeInTheDocument();
    });

    it('should prioritize error over empty', () => {
      render(
        <PageWrapper error="Error" hasData={false} empty={{ title: 'No data' }}>
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      expect(screen.getByText('页面加载失败')).toBeInTheDocument();
      expect(screen.queryByText('No data')).not.toBeInTheDocument();
    });

    it('should prioritize loading over empty', () => {
      render(
        <PageWrapper loading hasData={false} empty={{ title: 'No data' }}>
          <div data-testid="content">Content</div>
        </PageWrapper>
      );
      expect(screen.queryByText('No data')).not.toBeInTheDocument();
      expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    });
  });
});
