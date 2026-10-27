/**
 * 申请支援 Modal — 工单生命周期「处理」环节（spec 2.2）
 * 工程师现场遇到疑难时，请求高级工程师协助或远程协助。
 */
import React, { useState } from 'react';
import { Modal, Form, Input, Button, message, Switch, InputNumber } from 'antd';
import { TeamOutlined } from '@ant-design/icons';
import { workorderAPI } from '../../../api';

const { TextArea } = Input;

interface SupportModalProps {
  open: boolean;
  orderId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const SupportModal: React.FC<SupportModalProps> = ({ open, orderId, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: {
    target_engineer_id?: number;
    reason: string;
    remote?: boolean;
  }) => {
    setSubmitting(true);
    try {
      await workorderAPI.support(orderId, {
        target_engineer_id: values.target_engineer_id ? Number(values.target_engineer_id) : undefined,
        reason: values.reason,
        remote: values.remote ?? false,
      });
      message.success('支援请求已提交');
      form.resetFields();
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('提交失败:' + (error?.response?.data?.detail || error?.message));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={(<><TeamOutlined /> 申请支援</>)}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ remote: false }}>
        <Form.Item name="target_engineer_id" label="指定协助工程师ID">
          <InputNumber style={{ width: '100%' }} placeholder="可选，留空则由系统指派高级工程师" />
        </Form.Item>
        <Form.Item name="reason" label="支援原因" rules={[{ required: true, message: '请说明需要支援的原因' }]}>
          <TextArea rows={3} placeholder="如：现场遇到疑难故障，需要高级工程师远程协助诊断" />
        </Form.Item>
        <Form.Item name="remote" label="远程协助" valuePropName="checked">
          <Switch checkedChildren="远程" unCheckedChildren="到场" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting}>
          提交支援请求
        </Button>
      </Form>
    </Modal>
  );
};

export default SupportModal;
