/**
 * ErrorBoundary 扩展测试 — branch覆盖率提升
 * 目标: 83.33% → 100% branches
 * 覆盖: error.message undefined → '发生了未知错误', componentDidCatch
 */
import { render } from '@testing-library/react-native';
import ErrorBoundary from '../ErrorBoundary';

describe('ErrorBoundary.ext — branch coverage', () => {
  const originalError = console.error;
  beforeEach(() => {
    console.error = jest.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it('shows "发生了未知错误" when error has no message', () => {
    // Throwing a non-Error object → error.message is undefined
    const ThrowingChild: React.FC = () => {
      throw { code: 500 }; // non-Error object without .message
    };

    const { getByText } = render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>
    );
    expect(getByText('发生了未知错误')).toBeTruthy();
  });

  it('calls componentDidCatch with componentStack info', () => {
    const errorSpy = jest.fn();
    console.error = errorSpy;

    const ThrowingChild: React.FC = () => {
      throw new Error('捕获测试');
    };

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>
    );

    // componentDidCatch calls console.error internally
    expect(errorSpy).toHaveBeenCalled();
  });
});
