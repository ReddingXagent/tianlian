/**
 * 转单弹窗 - 下拉选择工程师 + 转单原因 + 确认
 */
import React, { useEffect, useState } from 'react';
import { Modal, Form, Select, Input, Button, message, Spin } from 'antd';
import { RollbackOutlined } from '@ant-design/icons';
import { userAPI } from '../../../api';

const { TextArea } = Input;

interface Engineer {
  id: number;
  real_name: string;
  username?: string;
}

interface TransferModalProps {
  visible: boolean;
  orderId: string;
  currentAssigneeId?: number | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const TransferModal: React.FC<TransferModalProps> = ({
  visible,
  orderId,
  currentAssigneeId,
  onCancel,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const [engineers, setEngineers] = useState<Engineer[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (visible) {
      fetchEngineers();
      form.resetFields();
    }
  }, [visible]);

  const fetchEngineers = async () => {
    setLoading(true);
    try {
      const { data } = await userAPI.engineers();
      // 后端返回分页格式或数组格式都兼容
      const items: Engineer[] = Array.isArray(data) ? data : (data.items || []);
      setEngineers(items.filter(e => e.id !== currentAssigneeId));
    } catch {
      message.warning('加载工程师列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values: { target_engineer_id: number; reason?: string }) => {
    setSubmitting(true);
    try {
      const api = (await import('../../../api')).default;
      await api.post(`/work-orders/${orderId}/transfer`, {
        target_engineer_id: values.target_engineer_id,
        reason: values.reason || '工作调整',
      });
      message.success('转单成功');
      onSuccess();
    } catch (err: unknown) {
      const error = err as any;
      message.error('转单失败: ' + (error?.response?.data?.detail || error?.message || '请重试'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={
        <span>
          <RollbackOutlined style={{ marginRight: 8 }} />
          转单 - {orderId}
        </span>
      }
      open={visible}
      onCancel={onCancel}
      footer={null}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        <Form.Item
          name="target_engineer_id"
          label="目标工程师"
          rules={[{ required: true, message: '请选择目标工程师' }]}
        >
          <Select
            showSearch
            placeholder="搜索并选择工程师"
            loading={loading}
            notFoundContent={loading ? <Spin size="small" /> : '无可用工程师'}
            filterOption={(input, option) =>
              (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
            }
            options={engineers.map(e => ({
              label: `${e.real_name}${e.username ? ` (@${e.username})` : ''}`,
              value: e.id,
            }))}
          />
        </Form.Item>
        <Form.Item name="reason" label="转单原因">
          <TextArea rows={3} placeholder="请输入转单原因（如：工作调整、技能不匹配等）" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block icon={<RollbackOutlined />}>
            确认转单
          </Button>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default TransferModal;
