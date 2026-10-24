/**
 * 预测性维护仪表盘
 * 
 * 显示：
 * 1. 设备健康度趋势图表
 * 2. 即将故障设备列表
 * 3. 预测统计卡片
 */
import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Table, Progress, Spin, Alert, Button, Tag } from 'antd';
import {
  WarningOutlined,
  CheckCircleOutlined,
  ThunderboltOutlined,
  LineChartOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import api from '../../api';

interface DashboardData {
  total_devices: number;
  healthy_devices: number;
  warning_devices: number;
  critical_devices: number;
  upcoming_failures: UpcomingFailure[];
  health_trend: HealthTrend[];
}

interface UpcomingFailure {
  device_id: string;
  device_name: string;
  failure_probability: number;
  predicted_failure_date: string;
  maintenance_recommendation: string;
}

interface HealthTrend {
  date: string;
  avg_health: number;
}

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const navigate = useNavigate();

  const goToDeviceDetail = (deviceId: string) => {
    navigate(`/devices?deviceId=${encodeURIComponent(deviceId)}`);
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/predictive-maintenance/dashboard');
      setData(response.data);
    } catch (err: any) {
      setError(err.message || '获取仪表盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  const failureColumns: ColumnsType<UpcomingFailure> = [
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      width: 150,
    },
    {
      title: '故障概率',
      dataIndex: 'failure_probability',
      key: 'failure_probability',
      width: 120,
      render: (prob: number) => {
        const color = prob > 0.8 ? '#ff4d4f' : prob > 0.5 ? '#faad14' : '#52c41a';
        return (
          <Progress 
            percent={Math.round(prob * 100)} 
            strokeColor={color}
            size="small"
          />
        );
      },
    },
    {
      title: '预测故障日期',
      dataIndex: 'predicted_failure_date',
      key: 'predicted_failure_date',
      width: 150,
    },
    {
      title: '维护建议',
      dataIndex: 'maintenance_recommendation',
      key: 'maintenance_recommendation',
      render: (text: string) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          onClick={() => goToDeviceDetail(record.device_id)}
        >
          详情
        </Button>
      ),
    },
  ];

  if (error) {
    return (
      <Alert 
        type="error" 
        message={error}
        action={<Button onClick={fetchDashboard}>重试</Button>}
      />
    );
  }

  if (loading || !data) {
    return (
      <div style={{ textAlign: 'center', padding: 50 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="设备总数"
              value={data.total_devices}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="健康设备"
              value={data.healthy_devices}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="预警设备"
              value={data.warning_devices}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="高风险设备"
              value={data.critical_devices}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 健康度趋势图 */}
      <Card 
        title="设备健康度趋势" 
        extra={<Button icon={<ReloadOutlined />} onClick={fetchDashboard}>刷新</Button>}
        style={{ marginBottom: 24 }}
      >
        <div style={{ height: 300, textAlign: 'center', padding: 50 }}>
          <LineChartOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <p style={{ color: '#999' }}>健康度趋势图表（需集成图表库）</p>
        </div>
      </Card>

      {/* 即将故障设备列表 */}
      <Card title="即将故障设备列表">
        <Table
          columns={failureColumns}
          dataSource={data.upcoming_failures}
          rowKey="device_id"
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  );
};

export default Dashboard;