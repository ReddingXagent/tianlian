import React, { useState, useEffect } from 'react';
import { 
  Card, Table, Button, Space, Input, Select, Tag, Modal, 
  Form, Row, Col, message, Descriptions, DatePicker 
} from 'antd';
import { 
  CalendarOutlined, EditOutlined, SaveOutlined, CloseOutlined,
  ClockCircleOutlined, HistoryOutlined 
} from '@ant-design/icons';
import { deviceAPI } from '../api';
import dayjs from 'dayjs';

const { Option } = Select;

interface MaintenancePlanProps {
  deviceId: number;
  initialData?: {
    maintenance_interval_days: number;
    last_maintenance: string | null;
    next_maintenance: string | null;
  };
}

interface MaintenanceRecord {
  id: number;
  type: string;
  status: string;
  title: string;
  description: string;
  cost: number;
  planned_at: string | null;
  completed_at: string | null;
  created_at: string;
}

const MaintenancePlanPanel: React.FC<MaintenancePlanProps> = ({ deviceId, initialData }) => {
  const [loading, setLoading] = useState(false);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [records, setRecords] = useState<MaintenanceRecord[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [form] = Form.useForm();
  const [plan, setPlan] = useState(initialData || {
    maintenance_interval_days: 90,
    last_maintenance: null,
    next_maintenance: null,
  });

  useEffect(() => {
    fetchRecords();
  }, [deviceId]);

  const fetchRecords = async () => {
    setRecordsLoading(true);
    try {
      const { data } = await deviceAPI.getMaintenanceRecords(deviceId);
      setRecords(data.items || []);
    } catch {
      // 静默处理：记录加载失败时不打断 UI，表格显示空
    } finally {
      setRecordsLoading(false);
    }
  };

  const handleSavePlan = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        // Convert date to string ISO format
        next_maintenance: values.next_maintenance ? values.next_maintenance.format('YYYY-MM-DD') : null,
        last_maintenance: values.last_maintenance ? values.last_maintenance.format('YYYY-MM-DD') : null,
      };
      await deviceAPI.updateMaintenancePlan(deviceId, payload);
      message.success('维护计划更新成功');
      setPlan({ ...plan, ...payload });
      setIsEditing(false);
    } catch (err: any) {
      message.error('更新失败: ' + (err?.response?.data?.detail || err.message));
    }
  };

  const recordColumns = [
    { 
      title: '时间', 
      dataIndex: 'completed_at', 
      key: 'completed_at', 
      width: 160,
      render: (t: string) => t ? dayjs(t).format('YYYY-MM-DD') : '计划中' 
    },
    { 
      title: '类型', 
      dataIndex: 'type', 
      key: 'type', 
      width: 100,
      render: (type: string) => {
        const colors: any = { preventive: 'blue', corrective: 'orange', emergency: 'red', condition_based: 'green' };
        return <Tag color={colors[type] || 'default'}>{type}</Tag>;
      }
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 100,
      render: (status: string) => <Tag>{status}</Tag>
    },
    { 
      title: '费用', 
      dataIndex: 'cost', 
      key: 'cost', 
      width: 100,
      render: (cost: number) => `¥${(cost / 100).toFixed(2)}` 
    },
  ];

  return (
    <div style={{ marginTop: 16 }}>
      <Card 
        title={<><CalendarOutlined /> 维护计划</>} 
        size="small" 
        extra={
          <Button 
            type="link" 
            icon={isEditing ? <SaveOutlined /> : <EditOutlined />} 
            onClick={() => isEditing ? handleSavePlan() : setIsEditing(true)}
          >
            {isEditing ? '保存' : '编辑计划'}
          </Button>
        }
      >
        {isEditing ? (
          <Form form={form} layout="vertical" initialValues={plan}>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="maintenance_interval_days" label="维护周期 (天)" rules={[{ required: true, type: 'number' }]}>
                  <Input type="number" min={1} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="last_maintenance" label="上次维护日期">
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="next_maintenance" label="下次维护日期">
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Button onClick={() => setIsEditing(false)} icon={<CloseOutlined />}>取消</Button>
          </Form>
        ) : (
          <Descriptions size="small" column={3}>
            <Descriptions.Item label="维护周期">
              <Tag color="blue">{plan.maintenance_interval_days} 天</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="上次维护">
              {plan.last_maintenance ? dayjs(plan.last_maintenance).format('YYYY-MM-DD') : '无记录'}
            </Descriptions.Item>
            <Descriptions.Item label="下次维护">
              <Tag color={dayjs().diff(dayjs(plan.next_maintenance), 'day') < 0 ? 'red' : 'orange'}>
                {plan.next_maintenance ? dayjs(plan.next_maintenance).format('YYYY-MM-DD') : '未设定'}
              </Tag>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card 
        title={<><HistoryOutlined /> 维护记录</>} 
        size="small" 
        style={{ marginTop: 16 }}
        extra={
          <Button size="small" onClick={fetchRecords} loading={recordsLoading}>刷新</Button>
        }
      >
        <Table 
          columns={recordColumns} 
          dataSource={records} 
          rowKey="id" 
          size="small" 
          loading={recordsLoading} 
          pagination={{ pageSize: 5 }}
          locale={{ emptyText: '暂无维护记录' }}
        />
      </Card>
    </div>
  );
};

export default MaintenancePlanPanel;
