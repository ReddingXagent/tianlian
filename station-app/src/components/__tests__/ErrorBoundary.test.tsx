import React from 'react';
import { Text } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import ErrorBoundary from '../ErrorBoundary';

function Bomb({ shouldThrow }: { shouldThrow: boolean }): React.ReactElement {
  if (shouldThrow) {
    throw new Error('boom');
  }
  return <Text>正常内容</Text>;
}

/** 重试后可恢复的子树：首次抛错，置位后不再抛 */
let recoverFlag = false;
function Recoverable(): React.ReactElement {
  if (!recoverFlag) {
    throw new Error('recoverable boom');
  }
  return <Text>恢复了</Text>;
}

describe('ErrorBoundary', () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    recoverFlag = false;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('should render children when no error', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    );
    expect(getByText('正常内容')).toBeTruthy();
  });

  it('should render fallback when child throws', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(getByText('😵')).toBeTruthy();
    expect(getByText('应用出现问题')).toBeTruthy();
    expect(getByText('重试')).toBeTruthy();
  });

  it('should log error via componentDidCatch', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      '[ErrorBoundary]',
      expect.any(Error),
      expect.anything()
    );
  });

  it('should re-render children after reset (retry button)', () => {
    // Recoverable 首次抛错，fallback 出现；按「重试」触发 setState 重置后重渲染子树
    const { getByText, queryByText } = render(
      <ErrorBoundary>
        <Recoverable />
      </ErrorBoundary>
    );
    expect(getByText('应用出现问题')).toBeTruthy();
    recoverFlag = true;
    fireEvent.press(getByText('重试'));
    expect(queryByText('应用出现问题')).toBeNull();
    expect(getByText('恢复了')).toBeTruthy();
  });
});
