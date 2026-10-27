/**
 * 申请备件 Modal — 工单生命周期「处理」环节（spec 2.2）
 * 现场需要更换物料时，提交备件申请（名称/型号/数量/原因），进入审批流。
 */
import React, { useState } from 'react';
import { Modal, Form, Input, Button, message, InputNumber } from 'antd';
import { ToolOutlined } from '@ant-design/icons';
import { workorderAPI } from '../../../api';

const { TextArea } = Input;

interface SparePartsModalProps {
  open: boolean;
  orderId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const SparePartsModal: React.FC<SparePartsModalProps> = ({ open, orderId, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: {
    part_name: string;
    part_model?: string;
    quantity: number;
    reason: string;
  }) => {
    setSubmitting(true);
    try {
      await workorderAPI.requestParts(orderId, {
        part_name: values.part_name,
        part_model: values.part_model,
        quantity: Number(values.quantity) || 1,
        reason: values.reason,
      });
      message.success('备件申请已提交，等待审批');
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
      title={(<><ToolOutlined /> 申请备件</>)}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ quantity: 1 }}
      >
        <Form.Item name="part_name" label="备件名称" rules={[{ required: true, message: '请输入备件名称' }]}>
          <Input placeholder="如：交流接触器" />
        </Form.Item>
        <Form.Item name="part_model" label="备件型号">
          <Input placeholder="如：CJX2-2510" />
        </Form.Item>
        <Form.Item name="quantity" label="数量" rules={[{ required: true, message: '请输入数量' }]}>
          <InputNumber min={1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="reason" label="申请原因" rules={[{ required: true, message: '请说明申请原因' }]}>
          <TextArea rows={3} placeholder="如：原接触器线圈烧毁，需更换" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting}>
          提交备件申请
        </Button>
      </Form>
    </Modal>
  );
};

export default SparePartsModal;
