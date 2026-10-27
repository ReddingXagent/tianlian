/**
 * DeviceControlPanel - 设备控制面板
 * 启动/停止/重启按钮 + 参数设置区域
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Button, Space, Input, message, Tag, Table, Spin, Popconfirm,
  Descriptions, Badge, Row, Col,
} from 'antd';
import {
  PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined,
  StopOutlined, SettingOutlined, HistoryOutlined,
} from '@ant-design/icons';
import { remoteAPI } from '../../api';
import { deviceAPI } from '../../api';

interface DeviceControlPanelProps {
  deviceId: number;
  deviceName: string;
  deviceType: string;
  deviceStatus: string;
}

interface DeviceHealth {
  health_score: number;
  health_status: string;
  health_status_display: string;
  dimension_scores?: Record<string, number>;
  checked_at?: string;
  last_health_check?: string;
}

interface ControlLog {
  id: number;
  device_id: number;
  device_name: string;
  action: string;
  parameter: string | null;
  value: string | null;
  params: Record<string, unknown> | null;
  result: string;
  message: string | null;
  operator: string | null;
  created_at: string;
}

const actionLabelMap: Record<string, { label: string; color: string }> = {
  start: { label: '启动', color: '#34a853' },
  stop: { label: '停止', color: '#ea4335' },
  restart: { label: '重启', color: '#ff5a36' },
  set_param: { label: '参数设置', color: '#722ed1' },
  emergency_stop: { label: '急停', color: '#ff0000' },
};

const DeviceControlPanel: React.FC<DeviceControlPanelProps> = ({
  deviceId,
  deviceName,
  deviceType,
  deviceStatus,
}) => {
  const [loading, setLoading] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<ControlLog[]>([]);
  const [paramName, setParamName] = useState('power_limit');
  const [paramValue, setParamValue] = useState('');
  const [health, setHealth] = useState<DeviceHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const isCharger = deviceType === 'charger_dc' || deviceType === 'charger_ac' ||
                    deviceType === 'CHARGER_DC' || deviceType === 'CHARGER_AC';

  useEffect(() => {
    if (deviceId) {
      fetchHistory();
      fetchHealth();
    }
  }, [deviceId]);

  const fetchHealth = async () => {
    setHealthLoading(true);
    try {
      const response = await deviceAPI.health(deviceId);
      setHealth(response.data);
    } catch {
      // 静默处理：健康度加载失败保留上次值
    } finally {
      setHealthLoading(false);
    }
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const { data } = await remoteAPI.history(deviceId);
      const respData = data as { items?: ControlLog[]; data?: ControlLog[] };
      setHistory(respData.items || respData.data || []);
    } catch {
      // 静默处理：控制历史加载失败保留上次值
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleControl = async (action: string) => {
    setLoading(action);
    try {
      const payload: Record<string, unknown> = { action };
      // For set_param, add parameter and value
      if (action === 'set_param') {
        payload.parameter = paramName;
        payload.value = paramValue;
      }

      await remoteAPI.control(deviceId, payload);
      message.success(`设备${actionLabelMap[action]?.label || action}成功`);
      fetchHistory();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || `设备控制失败`);
    } finally {
      setLoading(null);
    }
  };

  const getDimensionLabel = (key: string): string => {
    const labels: Record<string, string> = {
      electrical: '电气安全',
      thermal: '热稳定性',
      communication: '通信可靠性',
      power_quality: '电能质量',
      mechanical: '机械寿命',
    };
    return labels[key] || key;
  };

  const historyColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (a: string) => {
        const info = actionLabelMap[a];
        return info ? <Tag color={info.color}>{info.label}</Tag> : a;
      },
    },
    {
      title: '参数',
      key: 'param',
      width: 150,
      render: (_: unknown, r: ControlLog) => {
        if (r.action === 'set_param') {
          return <span>{r.parameter}={r.value}</span>;
        }
        return '-';
      },
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 80,
      render: (r: string) => (
        <Badge
          status={r === 'success' ? 'success' : 'error'}
          text={r === 'success' ? '成功' : '失败'}
        />
      ),
    },
    {
      title: '信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (m: string | null) => m || '-',
    },
  ];

  if (!isCharger) {
    return (
      <Card title="设备控制" size="small">
        <div style={{ textAlign: 'center', padding: 16, color: '#999' }}>
          仅支持充电桩类型设备控制
        </div>
      </Card>
    );
  }

  return (
    <div>
      {/* 控制按钮区 */}
      <Card title="设备控制" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label="设备名称">{deviceName}</Descriptions.Item>
          <Descriptions.Item label="当前状态">
            <Tag color={deviceStatus === 'online' ? 'green' : 'red'}>
              {deviceStatus === 'online' ? '在线' : deviceStatus === 'charging' ? '充电中' : deviceStatus}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="健康度评分">
            {healthLoading ? (
              <span>加载中...</span>
            ) : health ? (
              <Space>
                <span style={{ fontSize: 16, fontWeight: 'bold', color: health.health_score >= 80 ? '#34a853' : health.health_score >= 50 ? '#f5a623' : '#ea4335' }}>
                  {health.health_score}
                </span>
                <Tag color={health.health_score >= 80 ? 'green' : health.health_score >= 50 ? 'gold' : 'red'}>
                  {health.health_status_display}
                </Tag>
              </Space>
            ) : (
              <span style={{ color: '#999' }}>暂无数据</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="上次检测">
            {health?.last_health_check ? new Date(health.last_health_check).toLocaleString('zh-CN') : health?.checked_at ? new Date(health.checked_at).toLocaleString('zh-CN') : '暂无'}
          </Descriptions.Item>
        </Descriptions>

        <Row gutter={[8, 12]}>
          <Col>
            <Popconfirm
              title="确认启动设备？"
              onConfirm={() => handleControl('start')}
              okText="确认"
              cancelText="取消"
            >
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={loading === 'start'}
                style={{ backgroundColor: '#34a853', borderColor: '#34a853' }}
              >
                启动
              </Button>
            </Popconfirm>
          </Col>
          <Col>
            <Popconfirm
              title="确认停止设备？"
              onConfirm={() => handleControl('stop')}
              okText="确认"
              cancelText="取消"
            >
              <Button
                type="primary"
                icon={<PauseCircleOutlined />}
                loading={loading === 'stop'}
                danger
              >
                停止
              </Button>
            </Popconfirm>
          </Col>
          <Col>
            <Popconfirm
              title="确认重启设备？"
              onConfirm={() => handleControl('restart')}
              okText="确认"
              cancelText="取消"
            >
              <Button
                icon={<ReloadOutlined />}
                loading={loading === 'restart'}
                style={{ color: '#ff5a36', borderColor: '#ff5a36' }}
              >
                重启
              </Button>
            </Popconfirm>
          </Col>
          <Col>
            <Popconfirm
              title="确认急停设备？此操作不可撤回"
              onConfirm={() => handleControl('emergency_stop')}
              okText="确认急停"
              okButtonProps={{ danger: true }}
              cancelText="取消"
            >
              <Button
                icon={<StopOutlined />}
                loading={loading === 'emergency_stop'}
                danger
              >
                急停
              </Button>
            </Popconfirm>
          </Col>
        </Row>
      </Card>

      {/* 健康度维度评分 */}
      {health?.dimension_scores && (
        <Card title="健康度维度评分" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]}>
            {Object.entries(health.dimension_scores).map(([key, score]) => {
              return (
              <Col key={key} xs={12} sm={6} md={4}>
                <div style={{ textAlign: 'center', padding: 8 }}>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: score >= 80 ? '#34a853' : score >= 50 ? '#f5a623' : '#ea4335' }}>
                    {score}
                  </div>
                  <div style={{ fontSize: 12, color: '#888' }}>{getDimensionLabel(key)}</div>
                </div>
              </Col>
              );
            })}
          </Row>
        </Card>
      )}

      <Card title="参数设置" size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <span>参数名:</span>
            <Input
              value={paramName}
              onChange={(e) => setParamName(e.target.value)}
              placeholder="参数名（如 power_limit）"
              style={{ width: 200 }}
            />
            <span>参数值:</span>
            <Input
              value={paramValue}
              onChange={(e) => setParamValue(e.target.value)}
              placeholder="参数值"
              style={{ width: 150 }}
            />
            <Button
              type="primary"
              icon={<SettingOutlined />}
              loading={loading === 'set_param'}
              onClick={() => handleControl('set_param')}
              disabled={!paramValue}
            >
              设置参数
            </Button>
          </Space>
          <div style={{ color: '#888', fontSize: 12 }}>
            可用参数: power_limit (功率限制), voltage_threshold_high (电压上限), voltage_threshold_low (电压下限), frequency_threshold (频率阈值)
          </div>
        </Space>
      </Card>

      {/* 控制历史 */}
      <Card
        title={<><HistoryOutlined /> 控制历史</>}
        size="small"
        extra={
          <Button size="small" onClick={fetchHistory} loading={historyLoading}>
            刷新
          </Button>
        }
      >
        <Table
          columns={historyColumns}
          dataSource={history}
          rowKey="id"
          loading={historyLoading}
          size="small"
          pagination={{ pageSize: 10, size: 'small' }}
          locale={{ emptyText: '暂无控制记录' }}
        />
      </Card>
    </div>
  );
};

export default DeviceControlPanel;
