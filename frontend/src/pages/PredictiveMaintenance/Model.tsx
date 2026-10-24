/**
 * 模型管理页面
 * 
 * 功能：
 * 1. 查看模型状态
 * 2. 触发模型训练
 * 3. 训练进度展示
 */
import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Table, 
  Button, 
  Tag, 
  Progress, 
  Modal, 
  Form, 
  Input, 
  Select, 
  Spin, 
  Alert, 
  Space,
  Descriptions,
  Statistic,
  Row,
  Col,
} from 'antd';
import {
  ApiOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import api from '../../api';

interface ModelStatus {
  model_id: string;
  model_name: string;
  model_type: string;
  version: string;
  status: 'trained' | 'training' | 'failed' | 'idle';
  accuracy: number;
  last_trained: string;
  training_progress: number;
}

const Model: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [trainingModalVisible, setTrainingModalVisible] = useState(false);
  const [trainingForm] = Form.useForm();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchModelStatus();
  }, []);

  const fetchModelStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/predictive-maintenance/model-status');
      const data = response.data?.models || [];
      setModels(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || '获取模型状态失败');
      setModels([
        { model_id: '1', model_name: '故障预测模型', model_type: 'LSTM', version: 'v2.1', status: 'trained', accuracy: 0.92, last_trained: '2026-05-20', training_progress: 100 },
        { model_id: '2', model_name: '健康度评估模型', model_type: 'RandomForest', version: 'v1.5', status: 'trained', accuracy: 0.88, last_trained: '2026-05-18', training_progress: 100 },
        { model_id: '3', model_name: '寿命预测模型', model_type: 'XGBoost', version: 'v3.0', status: 'idle', accuracy: 0, last_trained: '-', training_progress: 0 },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleTrainModel = async (values: any) => {
    try {
      await api.post('/predictive-maintenance/train', {
        model_type: values.model_type,
        training_params: values.training_params,
      });
      setTrainingModalVisible(false);
      trainingForm.resetFields();
      fetchModelStatus();
    } catch (err: any) {
      setError(err.message || '触发训练失败');
      // 模拟训练
      setTrainingModalVisible(false);
      trainingForm.resetFields();
      setModels(prev => prev.map(m => 
        m.model_type === values.model_type 
          ? { ...m, status: 'training', training_progress: 0 }
          : m
      ));
      // 模拟训练进度
      const interval = setInterval(() => {
        setModels(prev => prev.map(m => {
          if (m.model_type === values.model_type) {
            const newProgress = Math.min(m.training_progress + 20, 100);
            return {
              ...m,
              training_progress: newProgress,
              status: newProgress === 100 ? 'trained' : 'training',
              accuracy: newProgress === 100 ? 0.85 : m.accuracy,
              last_trained: newProgress === 100 ? new Date().toISOString().split('T')[0] : m.last_trained,
            };
          }
          return m;
        }));
      }, 1000);
      setTimeout(() => clearInterval(interval), 5000);
    }
  };

  const columns: ColumnsType<ModelStatus> = [
    {
      title: '模型名称',
      dataIndex: 'model_name',
      key: 'model_name',
      width: 150,
    },
    {
      title: '模型类型',
      dataIndex: 'model_type',
      key: 'model_type',
      width: 120,
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string, record) => {
        const statusConfig: Record<string, { color: string; icon: React.ReactNode }> = {
          trained: { color: 'success', icon: <CheckCircleOutlined /> },
          training: { color: 'processing', icon: <SyncOutlined spin /> },
          failed: { color: 'error', icon: <ExclamationCircleOutlined /> },
          idle: { color: 'default', icon: <ClockCircleOutlined /> },
        };
        const config = statusConfig[status] || statusConfig.idle;
        return (
          <Tag color={config.color} icon={config.icon}>
            {status === 'training' ? `训练中 ${record.training_progress}%` : status}
          </Tag>
        );
      },
    },
    {
      title: '准确率',
      dataIndex: 'accuracy',
      key: 'accuracy',
      width: 100,
      render: (acc: number) => acc > 0 ? `${(acc * 100).toFixed(1)}%` : '-',
    },
    {
      title: '上次训练',
      dataIndex: 'last_trained',
      key: 'last_trained',
      width: 120,
    },
    {
      title: '训练进度',
      dataIndex: 'training_progress',
      key: 'training_progress',
      width: 150,
      render: (progress: number) => (
        <Progress 
          percent={progress} 
          size="small" 
          strokeColor={progress === 100 ? '#52c41a' : '#1890ff'}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button 
          type="link" 
          size="small"
          disabled={record.status === 'training'}
          onClick={() => {
            trainingForm.setFieldsValue({ model_type: record.model_type });
            setTrainingModalVisible(true);
          }}
        >
          重新训练
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

      {/* 模型统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="模型总数"
              value={models.length}
              prefix={<ApiOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已训练"
              value={models.filter(m => m.status === 'trained').length}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="训练中"
              value={models.filter(m => m.status === 'training').length}
              prefix={<SyncOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均准确率"
              value={models.filter(m => m.accuracy > 0).reduce((sum, m) => sum + m.accuracy, 0) / models.filter(m => m.accuracy > 0).length * 100 || 0}
              suffix="%"
              precision={1}
            />
          </Card>
        </Col>
      </Row>

      {/* 模型列表 */}
      <Card 
        title="模型列表" 
        extra={
          <Button 
            type="primary" 
            icon={<SyncOutlined />}
            onClick={() => setTrainingModalVisible(true)}
          >
            训练新模型
          </Button>
        }
      >
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={models}
            rowKey="model_id"
            pagination={false}
          />
        </Spin>
      </Card>

      {/* 训练模型弹窗 */}
      <Modal
        title="训练模型"
        open={trainingModalVisible}
        onCancel={() => {
          setTrainingModalVisible(false);
          trainingForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={trainingForm}
          layout="vertical"
          onFinish={handleTrainModel}
        >
          <Form.Item
            name="model_type"
            label="模型类型"
            rules={[{ required: true, message: '请选择模型类型' }]}
          >
            <Select
              placeholder="请选择模型类型"
              options={[
                { value: 'LSTM', label: 'LSTM (长短期记忆网络)' },
                { value: 'RandomForest', label: 'RandomForest (随机森林)' },
                { value: 'XGBoost', label: 'XGBoost (极端梯度提升)' },
                { value: 'Transformer', label: 'Transformer (注意力机制)' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="training_params"
            label="训练参数 (JSON格式)"
          >
            <Input.TextArea 
              placeholder='{"epochs": 100, "batch_size": 32}'
              rows={4}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                开始训练
              </Button>
              <Button onClick={() => {
                setTrainingModalVisible(false);
                trainingForm.resetFields();
              }}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Model;