/**
 * 通用平台管理占位页面
 */
import React from 'react';
import { Card, Typography, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;

interface PlaceholderProps {
  title: string;
  description: string;
  icon: React.ReactNode;
}

const PlaceholderPage: React.FC<PlaceholderProps> = ({ title, description, icon }) => {
  const navigate = useNavigate();
  return (
    <div style={{ padding: 24, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Card style={{ maxWidth: 480, textAlign: 'center', width: '100%' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>{icon}</div>
        <Title level={4}>{title}</Title>
        <Paragraph type="secondary">{description}</Paragraph>
        <Button type="primary" onClick={() => navigate(-1)}>返回</Button>
      </Card>
    </div>
  );
};

export default PlaceholderPage;
