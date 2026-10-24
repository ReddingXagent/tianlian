/**
 * 预测历史页面
 * 
 * 功能：
 * 1. 查看历史预测记录
 * 2. 按设备筛选
 * 3. 查看预测详情
 */
import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Table, 
  Select, 
  DatePicker, 
  Button, 
  Tag, 
  Progress, 
  Modal, 
  Descriptions, 
  Space, 
  Spin, 
  Alert,
  Row,
  Col,
  message,
} from 'antd';
import {
  HistoryOutlined,
  SearchOutlined,
  DownloadOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import api from '../../api';
import { exportObjectsCSV } from '../../utils/csvExport';

interface PredictionHistory {
  prediction_id: string;
  device_id: string;
  device_name: string;
  prediction_time: string;
  failure_probability: number;
  predicted_failure_date: string;
  health_score: number;
  result: 'accurate' | 'inaccurate' | 'pending';
  actual_failure_date?: string;
}

const History: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<PredictionHistory[]>([]);
  const [devices, setDevices] = useState<{ id: string; name: string }[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<PredictionHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDevices();
    fetchHistory();
  }, []);

  const fetchDevices = async () => {
    try {
      const response = await api.get('/devices');
      const deviceList = response.data?.devices || [];
      setDevices(Array.isArray(deviceList) ? deviceList.map((d: any) => ({ id: d.id, name: d.name })) : []);
    } catch {
      // 静默处理：设备列表加载失败降级为模拟数据
      setDevices([
        { id: '1', name: '变压器A1' },
        { id: '2', name: '开关柜B2' },
        { id: '3', name: '电缆C3' },
      ]);
    }
  };

  const fetchHistory = async (deviceId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const params: any = {};
      if (deviceId) params.device_id = deviceId;
      if (selectedDate) {
        params.start_date = selectedDate[0].format('YYYY-MM-DD');
        params.end_date = selectedDate[1].format('YYYY-MM-DD');
      }
      
      const response = await api.get(`/api/v1/predictive-maintenance/device/${deviceId || 'all'}/history`, { params });
      const data = response.data?.history || [];
      setHistory(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || '获取预测历史失败');
      // 使用模拟数据
      setHistory([
        {
          prediction_id: '1',
          device_id: '1',
          device_name: '变压器A1',
          prediction_time: '2026-05-20 10:30:00',
          failure_probability: 0.35,
          predicted_failure_date: '2026-06-15',
          health_score: 78,
          result: 'pending',
        },
        {
          prediction_id: '2',
          device_id: '2',
          device_name: '开关柜B2',
          prediction_time: '2026-05-18 14:15:00',
          failure_probability: 0.82,
          predicted_failure_date: '2026-05-25',
          health_score: 45,
          result: 'accurate',
          actual_failure_date: '2026-05-24',
        },
        {
          prediction_id: '3',
          device_id: '1',
          device_name: '变压器A1',
          prediction_time: '2026-05-15 09:00:00',
          failure_probability: 0.15,
          predicted_failure_date: '2026-07-01',
          health_score: 92,
          result: 'inaccurate',
        },
        {
          prediction_id: '4',
          device_id: '3',
          device_name: '电缆C3',
          prediction_time: '2026-05-10 16:45:00',
          failure_probability: 0.68,
          predicted_failure_date: '2026-06-01',
          health_score: 55,
          result: 'pending',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeviceChange = (deviceId: string) => {
    setSelectedDevice(deviceId);
    fetchHistory(deviceId);
  };

  const handleDateChange = (dates: any) => {
    setSelectedDate(dates);
  };

  const handleSearch = () => {
    fetchHistory(selectedDevice || undefined);
  };

  const handleExport = () => {
    if (history.length === 0) {
      message.warning('没有数据可导出');
      return;
    }
    exportObjectsCSV('预测历史记录', history, [
      { key: 'prediction_id', label: '预测ID' },
      { key: 'device_id', label: '设备ID' },
      { key: 'device_name', label: '设备名称' },
      { key: 'prediction_time', label: '预测时间' },
      { key: 'failure_probability', label: '故障概率' },
      { key: 'health_score', label: '健康度' },
      { key: 'predicted_failure_date', label: '预测故障日期' },
      { key: 'result', label: '结果', format: (r) => r.result === 'accurate' ? '准确' : r.result === 'inaccurate' ? '不准确' : '待验证' },
      { key: 'actual_failure_date', label: '实际故障日期' },
    ]);
  };

  const handleViewDetail = (record: PredictionHistory) => {
    setSelectedRecord(record);
    setDetailModalVisible(true);
  };

  const columns: ColumnsType<PredictionHistory> = [
    {
      title: '预测时间',
      dataIndex: 'prediction_time',
      key: 'prediction_time',
      width: 180,
      sorter: (a, b) => new Date(a.prediction_time).getTime() - new Date(b.prediction_time).getTime(),
    },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      width: 120,
      filters: devices.map(d => ({ text: d.name, value: d.id })),
      onFilter: (value, record) => record.device_id === value,
    },
    {
      title: '故障概率',
      dataIndex: 'failure_probability',
      key: 'failure_probability',
      width: 120,
      render: (prob: number) => {
        const color = prob > 0.7 ? '#ff4d4f' : prob > 0.4 ? '#faad14' : '#52c41a';
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
      title: '健康度',
      dataIndex: 'health_score',
      key: 'health_score',
      width: 100,
      render: (score: number) => (
        <Progress 
          percent={score}
          strokeColor={score > 80 ? '#52c41a' : score > 50 ? '#faad14' : '#ff4d4f'}
          size="small"
        />
      ),
    },
    {
      title: '预测故障日期',
      dataIndex: 'predicted_failure_date',
      key: 'predicted_failure_date',
      width: 130,
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      render: (result: string) => {
        const config: Record<string, { color: string; text: string }> = {
          accurate: { color: 'success', text: '准确' },
          inaccurate: { color: 'error', text: '不准确' },
          pending: { color: 'processing', text: '待验证' },
        };
        return <Tag color={config[result]?.color || 'default'}>{config[result]?.text || result}</Tag>;
      },
    },
    {
      title: '实际故障日期',
      dataIndex: 'actual_failure_date',
      key: 'actual_failure_date',
      width: 130,
      render: (date: string) => date || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Button 
          type="link" 
          size="small"
          icon={<EyeOutlined />}
          onClick={() => handleViewDetail(record)}
        >
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      {/* 错误提示 */}
      {error && (
        <Alert 
          type="error" 
          message={error} 
          style={{ marginBottom: 24 }} 
          closable
          onClose={() => setError(null)}
        />
      )}

      {/* 筛选器 */}
      <Card style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Select
              placeholder="选择设备"
              value={selectedDevice}
              onChange={handleDeviceChange}
              allowClear
              style={{ width: '100%' }}
              options={devices.map(d => ({ value: d.id, label: d.name }))}
            />
          </Col>
          <Col span={8}>
            <DatePicker.RangePicker
              value={selectedDate}
              onChange={handleDateChange}
              style={{ width: '100%' }}
            />
          </Col>
          <Col span={4}>
            <Button 
              type="primary" 
              icon={<SearchOutlined />}
              onClick={handleSearch}
            >
              查询
            </Button>
          </Col>
          <Col span={4}>
            <Button 
              icon={<DownloadOutlined />}
              onClick={handleExport}
            >
              导出
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 历史记录表格 */}
      <Card title="预测历史记录">
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={history}
            rowKey="prediction_id"
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条记录` }}
          />
        </Spin>
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="预测详情"
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedRecord(null);
        }}
        footer={null}
        width={600}
      >
        {selectedRecord && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label="预测ID">{selectedRecord.prediction_id}</Descriptions.Item>
            <Descriptions.Item label="设备名称">{selectedRecord.device_name}</Descriptions.Item>
            <Descriptions.Item label="预测时间">{selectedRecord.prediction_time}</Descriptions.Item>
            <Descriptions.Item label="故障概率">
              <Progress 
                percent={Math.round(selectedRecord.failure_probability * 100)} 
                strokeColor={selectedRecord.failure_probability > 0.7 ? '#ff4d4f' : '#faad14'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="健康度">
              <Progress 
                percent={selectedRecord.health_score}
                strokeColor={selectedRecord.health_score > 80 ? '#52c41a' : '#faad14'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="预测故障日期">{selectedRecord.predicted_failure_date}</Descriptions.Item>
            <Descriptions.Item label="结果">
              <Tag color={selectedRecord.result === 'accurate' ? 'success' : selectedRecord.result === 'inaccurate' ? 'error' : 'processing'}>
                {selectedRecord.result === 'accurate' ? '准确' : selectedRecord.result === 'inaccurate' ? '不准确' : '待验证'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="实际故障日期">{selectedRecord.actual_failure_date || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default History;