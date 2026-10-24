/**
 * LoadingSpinner - 通用加载指示器
 *
 * 支持:
 * - 全屏居中
 * - 内联行内
 * - 自定义文案
 * - 自定义大小
 * - 延迟显示 (避免闪烁)
 */
import React, { useState, useEffect } from 'react';
import { Spin, Typography } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface LoadingSpinnerProps {
  /** 模式: page 全屏 | section 区块 | inline 行内 */
  mode?: 'page' | 'section' | 'inline';
  /** 文案 (默认: 加载中...) */
  text?: string;
  /** 图标大小 */
  size?: number;
  /** 延迟显示 (ms, 默认 200，避免请求很快完成时闪烁) */
  delay?: number;
  /** 是否透明背景 */
  transparent?: boolean;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  mode = 'section',
  text = '加载中...',
  size = 32,
  delay = 200,
  transparent = false,
  style,
}) => {
  const [show, setShow] = useState(delay <= 0);

  useEffect(() => {
    if (delay <= 0) {
      setShow(true);
      return;
    }
    const timer = setTimeout(() => setShow(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  if (!show) return null;

  const indicator = <LoadingOutlined style={{ fontSize: size }} spin />;

  const inlineStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    flexDirection: 'column',
    gap: 12,
    ...style,
  };

  if (mode === 'page') {
    return (
      <div
        style={{
          ...inlineStyle,
          minHeight: '100vh',
          background: transparent ? 'transparent' : 'var(--bg-layout)',
        }}
      >
        <Spin indicator={indicator} />
        {text && (
          <Text style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
            {text}
          </Text>
        )}
      </div>
    );
  }

  if (mode === 'inline') {
    return (
      <span style={{ ...inlineStyle, display: 'inline-flex', gap: 6 }}>
        <Spin indicator={<LoadingOutlined style={{ fontSize: size * 0.6 }} spin />} />
        {text && (
          <Text style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            {text}
          </Text>
        )}
      </span>
    );
  }

  // section mode (default)
  return (
    <div
      style={{
        ...inlineStyle,
        minHeight: 240,
        padding: 48,
        background: transparent ? 'transparent' : 'var(--bg-card)',
        borderRadius: 8,
      }}
    >
      <Spin indicator={indicator} />
      {text && (
        <Text style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
          {text}
        </Text>
      )}
    </div>
  );
};

export default LoadingSpinner;