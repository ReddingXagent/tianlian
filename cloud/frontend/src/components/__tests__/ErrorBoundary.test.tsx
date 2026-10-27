/**
 * ErrorBoundary 组件单元测试（适配新版 ErrorBoundary）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from '../ErrorBoundary';

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const ThrowingComponent = () => {
    throw new Error('Test error');
  };

  it('should render children when no error', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">Hello World</div>
      </ErrorBoundary>
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.getByText('Hello World')).toBeInTheDocument();
  });

  it('should show error UI when child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    // Check that the error message is shown (wrapped in Text component)
    expect(screen.getByText('页面渲染出错')).toBeInTheDocument();
    expect(screen.getByText('Test error')).toBeInTheDocument();
    // Should have buttons: 复制错误信息, 重试, 返回首页
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(3);
  });

  it('should show generic error message when no error message', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    const SilentThrower = () => {
      throw new Error('');
    };

    render(
      <ErrorBoundary>
        <SilentThrower />
      </ErrorBoundary>
    );

    // With empty error message, it shows "未知错误"
    expect(screen.getByText('未知错误')).toBeInTheDocument();
  });

  it('should use Result component with error status', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    const result = document.querySelector('.ant-result');
    expect(result).toBeInTheDocument();
    expect(result).toHaveClass('ant-result-error');
  });

  it('should handle multiple children', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child1">First</div>
        <div data-testid="child2">Second</div>
      </ErrorBoundary>
    );

    expect(screen.getByTestId('child1')).toBeInTheDocument();
    expect(screen.getByTestId('child2')).toBeInTheDocument();
  });

  it('should render custom fallback when provided', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<div data-testid="custom-fallback">自定义降级UI</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
    expect(screen.getByText('自定义降级UI')).toBeInTheDocument();
  });
});