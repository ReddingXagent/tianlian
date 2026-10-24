/**
 * 验收评价 Modal — 工单生命周期「验收/评价」环节（spec 2.2）
 * 站长方对工单处理结果进行三维度星级评价：响应速度 / 维修质量 / 服务态度 + 文字评价。
 */
import React, { useState } from 'react';
import { Modal, Form, Rate, Input, Button, message } from 'antd';
import { StarOutlined } from '@ant-design/icons';
import { workorderAPI } from '../../../api';

const { TextArea } = Input;

interface RatingModalProps {
  open: boolean;
  orderId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const RatingModal: React.FC<RatingModalProps> = ({ open, orderId, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: {
    response_rating: number;
    quality_rating: number;
    attitude_rating: number;
    comment?: string;
  }) => {
    setSubmitting(true);
    try {
      await workorderAPI.rate(orderId, {
        response_rating: Number(values.response_rating) || 0,
        quality_rating: Number(values.quality_rating) || 0,
        attitude_rating: Number(values.attitude_rating) || 0,
        comment: values.comment,
      });
      message.success('评价已提交，工单验收完成');
      form.resetFields();
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('提交失败:' + (error?.response?.data?.detail || error?.message));
    } finally {
      setSubmitting(false);
    }
  };

  const fieldStyle: React.CSSProperties = { marginBottom: 8 };

  return (
    <Modal
      title={(<><StarOutlined /> 验收评价</>)}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ response_rating: 5, quality_rating: 5, attitude_rating: 5 }}
      >
        <Form.Item name="response_rating" label="响应速度" style={fieldStyle}>
          <Rate />
        </Form.Item>
        <Form.Item name="quality_rating" label="维修质量" style={fieldStyle}>
          <Rate />
        </Form.Item>
        <Form.Item name="attitude_rating" label="服务态度" style={fieldStyle}>
          <Rate />
        </Form.Item>
        <Form.Item name="comment" label="文字评价">
          <TextArea rows={3} placeholder="对本次运维服务的整体评价（可选）" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting}>
          提交评价并完成验收
        </Button>
      </Form>
    </Modal>
  );
};

export default RatingModal;
