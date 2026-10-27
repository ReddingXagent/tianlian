/**
 * 巡检结果录入 Modal — spec 2.5 巡检执行结果记录
 * 逐项录入：巡检项 / 实测值 / 正常·异常 / 异常描述，提交后写入 inspection_results。
 */
import React, { useEffect } from 'react';
import { Modal, Form, Input, Select, Button, Space, message } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { inspectionAPI } from '../../../api';

interface ResultItem {
  item_name?: string;
  value?: string;
  result?: 'normal' | 'abnormal';
  abnormal_desc?: string;
}

interface ResultRecordModalProps {
  open: boolean;
  taskId: number | null;
  taskName?: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const ResultRecordModal: React.FC<ResultRecordModalProps> = ({ open, taskId, taskName, onCancel, onSuccess }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleSubmit = async (values: { results?: ResultItem[] }) => {
    if (taskId == null) {
      message.warning('未选择巡检任务');
      return;
    }
    const results = (values.results || []).filter((it) => it && it.item_name);
    if (results.length === 0) {
      message.warning('请至少录入一条有效的巡检结果');
      return;
    }
    try {
      await inspectionAPI.results.create(taskId, { results });
      message.success('巡检结果已保存');
      form.resetFields();
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('保存失败:' + (error?.response?.data?.detail || error?.message));
    }
  };

  return (
    <Modal
      title={`巡检结果录入${taskName ? ' - ' + taskName : ''}`}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
      width={680}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ results: [{ item_name: '', value: '', result: 'normal', abnormal_desc: '' }] }}
      >
        <Form.List name="results">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="baseline" wrap>
                  <Form.Item name={[field.name, 'item_name']} noStyle>
                    <Input placeholder="巡检项" style={{ width: 150 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'value']} noStyle>
                    <Input placeholder="实测值" style={{ width: 110 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'result']} noStyle>
                    <Select
                      style={{ width: 100 }}
                      options={[
                        { label: '正常', value: 'normal' },
                        { label: '异常', value: 'abnormal' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name={[field.name, 'abnormal_desc']} noStyle>
                    <Input placeholder="异常描述（可选）" style={{ width: 160 }} />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(field.name)} />
                </Space>
              ))}
              <Button
                type="dashed"
                onClick={() => add({ item_name: '', value: '', result: 'normal', abnormal_desc: '' })}
                icon={<PlusOutlined />}
                block
              >
                添加巡检项
              </Button>
            </>
          )}
        </Form.List>
        <Button type="primary" htmlType="submit" block style={{ marginTop: 8 }}>
          保存巡检结果
        </Button>
      </Form>
    </Modal>
  );
};

export default ResultRecordModal;
