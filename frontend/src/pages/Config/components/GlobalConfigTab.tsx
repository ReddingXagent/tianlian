/**
 * 天链 V3 - 系统配置：全局配置 Tab
 */
import React from 'react';
import { Card, Form, Input, Select, Button, Space } from 'antd';
import { SettingOutlined, SaveOutlined } from '@ant-design/icons';
import { useGlobalConfig } from '../hooks/useGlobalConfig';

const { Option } = Select;

const GlobalConfigTab: React.FC = () => {
  const { globalLoading, globalForm, handleGlobalSave } = useGlobalConfig();

  return (
    <Card loading={globalLoading} title={<Space><SettingOutlined /> 系统全局设置</Space>}
      extra={<Button type="primary" icon={<SaveOutlined />} onClick={handleGlobalSave}>保存</Button>}>
      <Form form={globalForm} layout="vertical" style={{ maxWidth: 600 }}>
        <Form.Item name="system_name" label="系统名称" rules={[{ required: true, message: '请输入系统名称' }]}>
          <Input placeholder="例如：天链云平台" />
        </Form.Item>
        <Form.Item name="logo_url" label="Logo URL">
          <Input placeholder="https://example.com/logo.png" />
        </Form.Item>
        <Form.Item name="copyright" label="版权信息">
          <Input placeholder="© 2024 天链科技. All rights reserved." />
        </Form.Item>
        <Form.Item name="login_bg_url" label="登录页背景URL">
          <Input placeholder="https://example.com/bg.jpg" />
        </Form.Item>
        <Form.Item name="language" label="系统语言">
          <Select placeholder="选择语言">
            <Option value="zh-CN">简体中文</Option>
            <Option value="en-US">English</Option>
            <Option value="ja-JP">日本語</Option>
          </Select>
        </Form.Item>
      </Form>
    </Card>
  );
};

export default GlobalConfigTab;
