import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import ConfirmDialog from '../ConfirmDialog';

const defaultProps = {
  visible: true,
  message: '确定要停止设备「充电桩A-01」吗？',
  onConfirm: jest.fn(),
  onCancel: jest.fn(),
};

describe('ConfirmDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render title and message when visible', () => {
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} title="远程控制确认" />
    );

    expect(getByText('远程控制确认')).toBeTruthy();
    expect(getByText('确定要停止设备「充电桩A-01」吗？')).toBeTruthy();
  });

  it('should use default labels when none provided', () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);

    expect(getByText('确定')).toBeTruthy();
    expect(getByText('取消')).toBeTruthy();
  });

  it('should render custom confirm/cancel labels', () => {
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} confirmLabel="确认停止" cancelLabel="再想想" />
    );

    expect(getByText('确认停止')).toBeTruthy();
    expect(getByText('再想想')).toBeTruthy();
  });

  it('should call onConfirm when confirm button pressed', () => {
    const onConfirm = jest.fn();
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} onConfirm={onConfirm} confirmLabel="确认停止" />
    );

    fireEvent.press(getByText('确认停止'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('should call onCancel when cancel button pressed', () => {
    const onCancel = jest.fn();
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} onCancel={onCancel} />
    );

    fireEvent.press(getByText('取消'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('should show loading indicator and hide confirm label when loading', () => {
    const { getByText, queryByText } = render(
      <ConfirmDialog {...defaultProps} confirmLabel="确认停止" loading />
    );

    // loading 时确认按钮文字被替换为 ActivityIndicator
    expect(queryByText('确认停止')).toBeNull();
    // 取消按钮仍可用
    expect(getByText('取消')).toBeTruthy();
  });

  it('should not render message when not visible', () => {
    const { queryByText } = render(
      <ConfirmDialog {...defaultProps} visible={false} />
    );

    expect(queryByText('确定要停止设备「充电桩A-01」吗？')).toBeNull();
  });
});
