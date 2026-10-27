import React from 'react';
import { ActivityIndicator } from 'react-native';
import { render } from '@testing-library/react-native';
import LoadingSpinner from '../LoadingSpinner';

describe('LoadingSpinner', () => {
  it('should render with default text', () => {
    const { getByText } = render(<LoadingSpinner />);
    expect(getByText('加载中...')).toBeTruthy();
  });

  it('should render with custom text', () => {
    const { getByText } = render(<LoadingSpinner text="正在同步..." />);
    expect(getByText('正在同步...')).toBeTruthy();
  });

  it('should hide text when text is empty string', () => {
    const { queryByText } = render(<LoadingSpinner text="" />);
    expect(queryByText('加载中...')).toBeNull();
  });

  it('should pass size and color to ActivityIndicator', () => {
    const { UNSAFE_getByType } = render(
      <LoadingSpinner size="small" color="#ff0000" />
    );
    const indicator = UNSAFE_getByType(ActivityIndicator);
    expect(indicator.props.size).toBe('small');
    expect(indicator.props.color).toBe('#ff0000');
  });
});
