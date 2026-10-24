import { copyToClipboard } from '../utils/clipboard';
import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Result, Button, Space, Typography } from 'antd';
import {
  ReloadOutlined,
  HomeOutlined,
  BugOutlined,
  CopyOutlined,
} from '@ant-design/icons';

const { Paragraph, Text } = Typography;

interface Props {
  children: ReactNode;
  /** 自定义降级 UI */
  fallback?: ReactNode;
  /** 错误回调 */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
  showDetails: boolean;
}

/**
 * 全局 Error Boundary - 防止组件渲染崩溃导致整个 App 白屏
 * 支持暗色模式、错误详情展开、复制错误信息
 */
class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    showDetails: false,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary] 组件渲染崩溃:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  private handleReload = () => {
    window.location.href = '/';
  };

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  private handleCopy = () => {
    const { error, errorInfo } = this.state;
    const text = [
      `Error: ${error?.message || 'Unknown'}`,
      `Stack: ${error?.stack || 'N/A'}`,
      `Component Stack: ${errorInfo?.componentStack || 'N/A'}`,
    ].join('\n\n');
    copyToClipboard(text).then((ok) => {
      if (!ok) console.warn('复制失败: 请手动选中文本复制');
    });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      const errorMsg = this.state.error?.message || '未知错误';
      const errorStack = this.state.error?.stack || '';
      const componentStack = this.state.errorInfo?.componentStack || '';

      return (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            background: 'var(--bg-layout)',
            padding: 24,
          }}
        >
          <Result
            icon={<BugOutlined style={{ color: 'var(--error-color)', fontSize: 64 }} />}
            status="error"
            title={
              <Text strong style={{ fontSize: 20, color: 'var(--text-primary)' }}>
                页面渲染出错
              </Text>
            }
            subTitle={
              <div style={{ maxWidth: 480, margin: '0 auto' }}>
                <Paragraph
                  style={{ color: 'var(--text-secondary)', marginBottom: 8 }}
                  ellipsis={{ rows: 2, expandable: false }}
                >
                  {errorMsg}
                </Paragraph>
                <Button
                  type="link"
                  size="small"
                  onClick={() => this.setState({ showDetails: !this.state.showDetails })}
                  style={{ padding: 0 }}
                >
                  {this.state.showDetails ? '收起详情' : '查看详情'}
                </Button>
                {this.state.showDetails && (
                  <div
                    style={{
                      marginTop: 8,
                      padding: 12,
                      background: 'var(--bg-secondary)',
                      borderRadius: 6,
                      fontSize: 12,
                      fontFamily: 'monospace',
                      maxHeight: 200,
                      overflow: 'auto',
                      textAlign: 'left',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {errorStack}
                    {componentStack && `\n\nComponent Stack:\n${componentStack}`}
                  </div>
                )}
              </div>
            }
            extra={
              <Space>
                <Button icon={<CopyOutlined />} onClick={this.handleCopy}>
                  复制错误信息
                </Button>
                <Button icon={<ReloadOutlined />} onClick={this.handleRetry}>
                  重试
                </Button>
                <Button type="primary" icon={<HomeOutlined />} onClick={this.handleReload}>
                  返回首页
                </Button>
              </Space>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
