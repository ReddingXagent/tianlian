import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('should render with default props', () => {
    const { getByText } = render(<EmptyState />);
    expect(getByText('📭')).toBeTruthy();
    expect(getByText('暂无数据')).toBeTruthy();
    expect(getByText('当前没有可显示的内容')).toBeTruthy();
  });

  it('should render with custom icon', () => {
    const { getByText } = render(<EmptyState icon="🔔" />);
    expect(getByText('🔔')).toBeTruthy();
  });

  it('should render with custom title', () => {
    const { getByText } = render(<EmptyState title="没有告警" />);
    expect(getByText('没有告警')).toBeTruthy();
  });

  it('should render with custom message', () => {
    const { getByText } = render(<EmptyState message="目前没有任何告警信息" />);
    expect(getByText('目前没有任何告警信息')).toBeTruthy();
  });

  it('should render action button when actionLabel and onAction provided', () => {
    const onAction = jest.fn();
    const { getByText } = render(
      <EmptyState actionLabel="刷新" onAction={onAction} />
    );
    const button = getByText('刷新');
    expect(button).toBeTruthy();
  });

  it('should call onAction when button pressed', () => {
    const onAction = jest.fn();
    const { getByText } = render(
      <EmptyState actionLabel="重试" onAction={onAction} />
    );
    fireEvent.press(getByText('重试'));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('should not render action button when only actionLabel provided without onAction', () => {
    const { queryByText } = render(<EmptyState actionLabel="刷新" />);
    expect(queryByText('刷新')).toBeNull();
  });

  it('should not render action button when only onAction provided without actionLabel', () => {
    const { queryByText } = render(<EmptyState onAction={jest.fn()} />);
    // Default button label should not appear when actionLabel is not provided
    expect(queryByText('刷新')).toBeNull();
  });

  it('should accept and render all custom props together', () => {
    const onAction = jest.fn();
    const { getByText } = render(
      <EmptyState
        icon="🚀"
        title="没有站点"
        message="请先添加一个充电站点"
        actionLabel="添加站点"
        onAction={onAction}
      />
    );
    expect(getByText('🚀')).toBeTruthy();
    expect(getByText('没有站点')).toBeTruthy();
    expect(getByText('请先添加一个充电站点')).toBeTruthy();
    expect(getByText('添加站点')).toBeTruthy();
  });
});