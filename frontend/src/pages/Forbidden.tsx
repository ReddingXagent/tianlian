/**
 * 403 权限不足页面
 */
import React from 'react';
import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getDefaultRoute } from '../utils/auth';

const ForbiddenPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Result
        status="403"
        title="403"
        subTitle="抱歉，您没有权限访问此页面。请联系管理员获取相应权限。"
        extra={
          <Button type="primary" onClick={() => navigate(getDefaultRoute())}>
            返回首页
          </Button>
        }
      />
    </div>
  );
};

export default ForbiddenPage;