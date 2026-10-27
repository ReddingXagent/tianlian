/**
 * 巡检模板编辑 Modal — spec 2.5 巡检模板
 * 定义模板名称、适用设备类型、巡检项动态列表（项名/单位/标准值）。
 */
import React, { useEffect } from 'react';
import { Modal, Form, Input, Select, Button, Space, message } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { inspectionAPI } from '../../../api';

const targetOptions = [
  { label: '全部设备', value: 'all' },
  { label: '逆变器', value: 'inverter' },
  { label: '储能系统', value: 'battery' },
  { label: '充电桩', value: 'charger' },
  { label: '网关', value: 'gateway' },
];

interface InspectionItem {
  name?: string;
  unit?: string;
  standard_value?: string;
}

interface TemplateModalProps {
  open: boolean;
  editing: Record<string, unknown> | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const TemplateModal: React.FC<TemplateModalProps> = ({ open, editing, onCancel, onSuccess }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (!open) return;
    if (editing) {
      form.setFieldsValue(editing);
    } else {
      form.resetFields();
    }
  }, [open, editing, form]);

  const handleSubmit = async (values: { name: string; target?: string; items?: InspectionItem[] }) => {
    // 过滤掉名称为空的巡检项
    const items = (values.items || []).filter((it) => it && it.name);
    const payload = { name: values.name, target: values.target || 'all', items };
    try {
      if (editing && (editing as { id?: number }).id != null) {
        await inspectionAPI.templates.update((editing as { id: number }).id, payload);
        message.success('模板已更新');
      } else {
        await inspectionAPI.templates.create(payload);
        message.success('模板已创建');
      }
      form.resetFields();
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('保存失败:' + (error?.response?.data?.detail || error?.message));
    }
  };

  return (
    <Modal
      title={editing ? `编辑模板 - ${editing.name ?? ''}` : '新建巡检模板'}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
      width={640}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ target: 'all', items: [{ name: '', unit: '', standard_value: '' }] }}
      >
        <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
          <Input placeholder="如：充电桩周巡检模板" />
        </Form.Item>
        <Form.Item name="target" label="适用设备类型">
          <Select options={targetOptions} />
        </Form.Item>
        <Form.Item label="巡检项">
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item name={[field.name, 'name']} noStyle>
                      <Input placeholder="巡检项名称" style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'unit']} noStyle>
                      <Input placeholder="单位" style={{ width: 90 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'standard_value']} noStyle>
                      <Input placeholder="标准值" style={{ width: 120 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add({ name: '', unit: '', standard_value: '' })}
                  icon={<PlusOutlined />}
                  block
                >
                  添加巡检项
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>
        <Button type="primary" htmlType="submit" block style={{ marginTop: 8 }}>
          保存模板
        </Button>
      </Form>
    </Modal>
  );
};

export default TemplateModal;
