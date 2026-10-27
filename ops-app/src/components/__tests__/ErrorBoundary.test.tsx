import { render, fireEvent } from '@testing-library/react-native';
import { Text } from 'react-native';
import ErrorBoundary from '../ErrorBoundary';

describe('ErrorBoundary', () => {
  // 抑制 console.error 输出
  const originalError = console.error;
  beforeEach(() => {
    console.error = jest.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it('renders children when no error', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <Text>正常内容</Text>
      </ErrorBoundary>
    );
    expect(getByText('正常内容')).toBeTruthy();
  });

  it('renders fallback UI when child throws', () => {
    const ThrowingChild: React.FC = () => {
      throw new Error('测试崩溃');
    };

    const { getByText } = render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>
    );
    expect(getByText('页面出错了')).toBeTruthy();
    expect(getByText('测试崩溃')).toBeTruthy();
  });

  it('renders custom fallback when provided', () => {
    const ThrowingChild: React.FC = () => {
      throw new Error('自定义');
    };

    const { getByText } = render(
      <ErrorBoundary fallback={<Text>自定义降级</Text>}>
        <ThrowingChild />
      </ErrorBoundary>
    );
    expect(getByText('自定义降级')).toBeTruthy();
  });

  it('resets error state when retry button pressed', () => {
    let shouldThrow = true;
    const ConditionalChild: React.FC = () => {
      if (shouldThrow) throw new Error('条件崩溃');
      return <Text>恢复正常</Text>;
    };

    const { getByText, queryByText } = render(
      <ErrorBoundary>
        <ConditionalChild />
      </ErrorBoundary>
    );
    expect(getByText('条件崩溃')).toBeTruthy();

    shouldThrow = false;
    fireEvent.press(getByText('重试'));
    expect(queryByText('条件崩溃')).toBeNull();
  });
});
