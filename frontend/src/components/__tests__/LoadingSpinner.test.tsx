/**
 * LoadingSpinner 组件测试
 */
import { render, screen } from '@testing-library/react';
import LoadingSpinner from '../LoadingSpinner';

describe('LoadingSpinner', () => {
  beforeAll(() => {
    // 模拟 CSS 变量
    document.documentElement.style.setProperty('--bg-layout', '#faf5f4');
    document.documentElement.style.setProperty('--bg-card', '#ffffff');
    document.documentElement.style.setProperty('--text-secondary', '#777270');
  });

  it('should render with default text', async () => {
    render(<LoadingSpinner mode="section" delay={0} />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('should render with custom text', () => {
    render(<LoadingSpinner text="数据加载中..." delay={0} />);
    expect(screen.getByText('数据加载中...')).toBeInTheDocument();
  });

  it('should render in page mode', () => {
    const { container } = render(<LoadingSpinner mode="page" delay={0} />);
    // Page mode should include text
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('should render in inline mode', () => {
    const { container } = render(<LoadingSpinner mode="inline" text="刷新中" delay={0} />);
    expect(screen.getByText('刷新中')).toBeInTheDocument();
  });

  it('should not render when delay has not elapsed (delay=1000)', () => {
    render(<LoadingSpinner delay={1000} />);
    expect(screen.queryByText('加载中...')).not.toBeInTheDocument();
  });

  it('should render immediately when delay=0', () => {
    render(<LoadingSpinner delay={0} />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('should render without text when text is empty', () => {
    render(<LoadingSpinner text="" />);
    expect(screen.queryByText('加载中...')).not.toBeInTheDocument();
  });

  it('should apply custom style', () => {
    const { container } = render(
      <LoadingSpinner style={{ backgroundColor: 'red' }} mode="inline" delay={0} />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toBeInTheDocument();
  });
});