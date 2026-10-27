/**
 * 创建工单弹窗
 */
import React from 'react';
import { Modal, Form, Input, Select, Button } from 'antd';
import type { FormInstance } from 'antd';

const { TextArea } = Input;

interface CreateWorkOrderModalProps {
  open: boolean;
  form: FormInstance;
  onCancel: () => void;
  onCreate: (values: { fault_desc: string; type?: string; level?: string; station_id?: number | null; device_id?: number | null }) => void;
}

const CreateWorkOrderModal: React.FC<CreateWorkOrderModalProps> = ({ open, form, onCancel, onCreate }) => (
  <Modal
    title="创建工单"
    open={open}
    onCancel={onCancel}
    footer={null}
  >
    <Form form={form} layout="vertical" onFinish={onCreate}>
      <Form.Item name="fault_desc" label="故障描述" rules={[{ required: true, message: '请输入故障描述' }]}>
        <TextArea rows={3} placeholder="请描述故障情况" />
      </Form.Item>
      <Form.Item name="type" label="工单类型" initialValue="repair">
        <Select options={[
          { label: '维修', value: 'repair' },
          { label: '巡检', value: 'inspection' },
          { label: '安装', value: 'installation' },
          { label: '保养', value: 'maintenance' },
        ]} />
      </Form.Item>
      <Form.Item name="level" label="优先级" initialValue="warning">
        <Select options={[
          { label: '低', value: 'low' },
          { label: '一般', value: 'warning' },
          { label: '高', value: 'high' },
          { label: '紧急', value: 'urgent' },
        ]} />
      </Form.Item>
      <Form.Item name="station_id" label="站点ID">
        <Input type="number" placeholder="可选" />
      </Form.Item>
      <Form.Item name="device_id" label="设备ID">
        <Input type="number" placeholder="可选" />
      </Form.Item>
      <Form.Item>
        <Button type="primary" htmlType="submit" block>创建</Button>
      </Form.Item>
    </Form>
  </Modal>
);

export default CreateWorkOrderModal;
