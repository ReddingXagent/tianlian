/**
 * ErrorBoundary 深色模式覆盖补测 — F3684 (夜间冲刺档 v2)
 * 目标: L23 Appearance.getColorScheme() === 'dark' → colorsDark 降级UI路径
 * (light 路径由现有两套 ErrorBoundary 测试覆盖; dark 路径 jest 环境默认 light 从未走通)
 */
import React from 'react';
import { render } from '@testing-library/react-native';
import { Appearance } from 'react-native';
import ErrorBoundary from '../ErrorBoundary';
import { colorsDark } from '../../theme/colors';

describe('ErrorBoundary — 深色模式降级UI (L23 dark路径)', () => {
  const originalError = console.error;
  beforeEach(() => {
    console.error = jest.fn();
  });
  afterEach(() => {
    console.error = originalError;
    jest.restoreAllMocks();
  });

  it('深色模式下降级UI使用colorsDark.pageBg背景', () => {
    jest.spyOn(Appearance, 'getColorScheme').mockReturnValue('dark');

    const ThrowingChild: React.FC = () => {
      throw new Error('深色模式崩溃');
    };

    const { getByText, root } = render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>
    );

    expect(getByText('页面出错了')).toBeTruthy();
    expect(getByText('深色模式崩溃')).toBeTruthy();

    // 验证走了 colorsDark: 降级容器 backgroundColor = colorsDark.pageBg
    const container = root.findAll(
      (n) =>
        Array.isArray(n.props.style) &&
        n.props.style.some(
          (s: { backgroundColor?: string }) => s?.backgroundColor === colorsDark.pageBg
        )
    );
    expect(container.length).toBeGreaterThan(0);
  });
});
