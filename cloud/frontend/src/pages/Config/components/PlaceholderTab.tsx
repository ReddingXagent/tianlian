/**
 * 配置多租户化 (卡 d0c431d0) — 团队专属面板占位
 *
 * 车队专属 / 运维专属配置面板的内容由后续卡实现, 此处仅提供
 * 文案 + 空态, 占据 Tab 位置, 让对应 team_type 用户提前看到入口。
 */
import React from 'react';
import { Empty, Typography } from 'antd';

const { Title, Paragraph } = Typography;

interface PlaceholderTabProps {
  /** 面板标题 (展示在空态下方) */
  title: string;
  /** 面板描述 / 后续卡说明 */
  description: string;
}

const PlaceholderTab: React.FC<PlaceholderTabProps> = ({ title, description }) => (
  <div style={{ padding: '40px 0', textAlign: 'center' }}>
    <Empty description={null} />
    <Title level={5} style={{ marginTop: 16 }}>
      {title}
    </Title>
    <Paragraph type="secondary" style={{ marginBottom: 0 }}>
      {description}
    </Paragraph>
  </div>
);

export default PlaceholderTab;
