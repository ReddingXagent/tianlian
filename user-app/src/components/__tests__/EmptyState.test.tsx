import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('renders default props', () => {
    const { getByText } = render(<EmptyState />);
    expect(getByText('📭')).toBeTruthy();
    expect(getByText('暂无数据')).toBeTruthy();
    expect(getByText('当前没有可显示的内容')).toBeTruthy();
  });

  it('renders custom content', () => {
    const { getByText } = render(
      <EmptyState
        icon="🔌"
        title="没有充电桩"
        message="该站点暂未安装充电桩"
      />
    );
    expect(getByText('🔌')).toBeTruthy();
    expect(getByText('没有充电桩')).toBeTruthy();
    expect(getByText('该站点暂未安装充电桩')).toBeTruthy();
  });

  it('renders action button when actionLabel and onAction provided', () => {
    const onAction = jest.fn();
    const { getByText } = render(
      <EmptyState
        title="加载失败"
        message="网络错误"
        actionLabel="重试"
        onAction={onAction}
      />
    );
    const button = getByText('重试');
    fireEvent.press(button);
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('does not render action button when actionLabel is missing', () => {
    const { queryByText } = render(
      <EmptyState title="暂无数据" message="空" />
    );
    expect(queryByText('重试')).toBeNull();
  });
});