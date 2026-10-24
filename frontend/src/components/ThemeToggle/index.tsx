/**
 * 主题切换组件 - 集成 ThemeContext
 * 暗黑模式切换开关，支持快捷键 Ctrl+Shift+D
 */
import React, { useEffect } from 'react';
import { Switch, Space, Typography } from 'antd';
import { BulbOutlined, BulbFilled } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';

const { Text } = Typography;

interface ThemeToggleProps {
  /** Display mode: compact or full */
  compact?: boolean;
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ compact = false }) => {
  const { isDark, toggleTheme } = useTheme();

  // Keyboard shortcut Ctrl+Shift+D
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        toggleTheme();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggleTheme]);

  if (compact) {
    return (
      <Switch
        checked={isDark}
        onChange={toggleTheme}
        checkedChildren={<BulbFilled style={{ fontSize: 12 }} />}
        unCheckedChildren={<BulbOutlined style={{ fontSize: 12 }} />}
        size="small"
      />
    );
  }

  return (
    <Space>
      {isDark ? <BulbFilled style={{ color: '#f5a623' }} /> : <BulbOutlined />}
      <Text>暗黑模式</Text>
      <Switch
        checked={isDark}
        onChange={toggleTheme}
        checkedChildren="🌙"
        unCheckedChildren="☀️"
      />
    </Space>
  );
};

export default ThemeToggle;
