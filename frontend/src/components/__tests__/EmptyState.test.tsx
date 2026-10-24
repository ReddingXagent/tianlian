import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('renders default empty state', () => {
    render(<EmptyState />);
    expect(screen.getByText('暂无数据')).toBeTruthy();
  });

  it('renders device empty state with correct text', () => {
    render(<EmptyState type="device" />);
    expect(screen.getByText('暂无设备')).toBeTruthy();
  });

  it('renders alarm empty state with correct text', () => {
    render(<EmptyState type="alarm" />);
    expect(screen.getByText('暂无告警')).toBeTruthy();
  });

  it('renders with action button', () => {
    const onAction = vi.fn();
    render(<EmptyState type="search" actionText="重新搜索" onAction={onAction} />);
    expect(screen.getByText('重新搜索')).toBeTruthy();
    fireEvent.click(screen.getByText('重新搜索'));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it('renders with custom title and description', () => {
    render(<EmptyState title="自定义标题" description="自定义描述" />);
    expect(screen.getByText('自定义标题')).toBeTruthy();
    expect(screen.getByText('自定义描述')).toBeTruthy();
  });

  it('renders without image when showImage is false', () => {
    const { container } = render(<EmptyState showImage={false} />);
    expect(screen.getByText('暂无数据')).toBeTruthy();
  });
});
