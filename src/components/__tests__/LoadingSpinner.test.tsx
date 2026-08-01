import { ActivityIndicator } from 'react-native';
import { render } from '@testing-library/react-native';
import LoadingSpinner from '../LoadingSpinner';

describe('LoadingSpinner', () => {
  it('should render with default props', () => {
    const { getByText, UNSAFE_getByType } = render(<LoadingSpinner />);
    expect(getByText('加载中...')).toBeTruthy();
    const indicator = UNSAFE_getByType(ActivityIndicator);
    expect(indicator.props.size).toBe('large');
    expect(indicator.props.color).toBe('#1a73e8');
  });

  it('should render custom text', () => {
    const { getByText } = render(<LoadingSpinner text="正在同步..." />);
    expect(getByText('正在同步...')).toBeTruthy();
  });

  it('should not render text when text is empty', () => {
    const { queryByText, UNSAFE_getByType } = render(<LoadingSpinner text="" />);
    expect(queryByText('加载中...')).toBeNull();
    // 指示器仍在
    expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
  });

  it('should pass custom size and color to indicator', () => {
    const { UNSAFE_getByType } = render(
      <LoadingSpinner size="small" color="#ff0000" />
    );
    const indicator = UNSAFE_getByType(ActivityIndicator);
    expect(indicator.props.size).toBe('small');
    expect(indicator.props.color).toBe('#ff0000');
  });
});
