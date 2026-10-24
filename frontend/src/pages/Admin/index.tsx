/**
 * 天链 V3 — 管理后台: 物联网接入
 * 互联互通 + 市政监管已迁移至运营平台 (/operate)
 * 本页面保留: 终端管理 + 云服务配置入口
 */
import React from 'react';
import { Card, Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

const AdminPage: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="page-container">
      <Card>
        <Result
          status="info"
          title="管理后台"
          subTitle="互联互通和市政监管已迁移至运营平台"
          extra={[
            <Button type="primary" key="interconnect" onClick={() => navigate('/interconnect')}>
              前往互联互通
            </Button>,
            <Button key="supervision" onClick={() => navigate('/supervision')}>
              前往市政监管
            </Button>,
          ]}
        />
      </Card>
    </div>
  );
};

export default AdminPage;
