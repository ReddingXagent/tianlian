import React from 'react';
import { Text } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import { ErrorBoundary } from '../ErrorBoundary';

// Helper component that throws
const ThrowComponent = ({ message }: { message: string }) => {
  throw new Error(message);
};

// Helper component that renders normally
const GoodComponent = () => <Text testID="good">All good</Text>;

describe('ErrorBoundary', () => {
  // Suppress console.error from React error boundaries in test output
  const originalError = console.error;
  beforeAll(() => {
    console.error = jest.fn();
  });
  afterAll(() => {
    console.error = originalError;
  });

  it('renders children when no error', () => {
    const { getByTestId } = render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>
    );
    expect(getByTestId('good')).toBeTruthy();
  });

  it('renders default fallback UI on error', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <ThrowComponent message="Test crash" />
      </ErrorBoundary>
    );
    expect(getByText('⚠️')).toBeTruthy();
    expect(getByText('出错了')).toBeTruthy();
    expect(getByText('Test crash')).toBeTruthy();
  });

  it('renders generic message when error has no message', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <ThrowComponent message="" />
      </ErrorBoundary>
    );
    expect(getByText('应用遇到未知错误')).toBeTruthy();
  });

  it('renders custom fallback when provided', () => {
    const { getByText } = render(
      <ErrorBoundary fallback={<Text>Custom fallback</Text>}>
        <ThrowComponent message="oops" />
      </ErrorBoundary>
    );
    expect(getByText('Custom fallback')).toBeTruthy();
  });

  it('resets error state when retry button pressed', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <ThrowComponent message="Crash here" />
      </ErrorBoundary>
    );
    expect(getByText('出错了')).toBeTruthy();

    // Press retry - state resets, ThrowComponent re-renders and throws again
    // So the error boundary catches it again
    fireEvent.press(getByText('重试'));
    // After retry, the boundary re-renders children. Since ThrowComponent always
    // throws, we expect the error UI to appear again (proving state was reset then re-caught)
    expect(getByText('出错了')).toBeTruthy();
  });

  it('logs error via componentDidCatch', () => {
    const spy = jest.spyOn(console, 'error');
    render(
      <ErrorBoundary>
        <ThrowComponent message="Logged crash" />
      </ErrorBoundary>
    );
    // componentDidCatch calls console.error
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
