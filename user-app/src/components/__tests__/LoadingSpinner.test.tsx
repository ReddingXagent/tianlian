import React from 'react';
import { render } from '@testing-library/react-native';
import LoadingSpinner from '../LoadingSpinner';

describe('LoadingSpinner', () => {
  it('renders default text', () => {
    const { getByText } = render(<LoadingSpinner />);
    expect(getByText('加载中...')).toBeTruthy();
  });

  it('renders custom text', () => {
    const { getByText } = render(<LoadingSpinner text="获取位置..." />);
    expect(getByText('获取位置...')).toBeTruthy();
  });

  it('renders without text when text is empty', () => {
    const { queryByText } = render(<LoadingSpinner text="" />);
    expect(queryByText('')).toBeNull();
  });
});