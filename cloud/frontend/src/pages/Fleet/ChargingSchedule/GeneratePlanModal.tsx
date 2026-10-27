/**
 * 生成调度计划表单
 *
 * 车辆多选(checkbox 列表) + 可用总功率 + 时间窗口
 * 提交 → POST /fleet/charging/schedule/generate
 */
import React, { useEffect } from 'react';
import { Modal, Form, InputNumber, Checkbox, Space, Button, Row, Col, message } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';

interface Props {
  open: boolean;
  enterpriseId: number;
  onCancel: () => void;
  onSuccess: () => void;
}

const DEFAULT_VEHICLES = [
  { enabled: true, vehicle_id: 1, current_soc: 0.3, target_soc: 0.9, max_power_kw: 7 },
  { enabled: true, vehicle_id: 2, current_soc: 0.4, target_soc: 0.9, max_power_kw: 7 },
];

const GeneratePlanModal: React.FC<Props> = ({ open, enterpriseId, onCancel, onSuccess }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        enterprise_id: enterpriseId,
        available_power_kw: 100,
        window_start: '00:00',
        window_end: '23:59',
        vehicles: DEFAULT_VEHICLES,
      });
    }
  }, [open, enterpriseId, form]);

  const handleSubmit = async () => {
    try {
      const v = await form.validateFields();
      const vehicle_states = (v.vehicles || [])
        .filter((x: any) => x?.enabled)
        .map(({ enabled: _enabled, ...rest }: any) => rest);
      if (vehicle_states.length === 0) {
        message.warning('请至少勾选一辆参与调度的车辆');
        return;
      }
      const today = dayjs().format('YYYY-MM-DD');
      await api.post('/fleet/charging/schedule/generate', {
        enterprise_id: v.enterprise_id,
        vehicle_states,
        available_power_kw: v.available_power_kw,
        time_window_start: `${today}T${v.window_start}:00`,
        time_window_end: `${today}T${v.window_end}:00`,
      });
      message.success('调度计划生成成功');
      onSuccess();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验失败,不提示
      message.error('生成失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  return (
    <Modal title="生成调度计划" open={open} onOk={handleSubmit} onCancel={onCancel}
      okText="确定" cancelText="取消" width={660}>
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="enterprise_id" label="企业ID" rules={[{ required: true, message: '请输入企业ID' }]}>
              <InputNumber style={{ width: '100%' }} min={1} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="available_power_kw" label="可用总功率(kW)" rules={[{ required: true, message: '请输入可用功率' }]}>
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="window_start" label="起始时间" rules={[{ required: true }]}>
              <input type="time" style={{ width: '100%', height: 32, padding: '0 4px', border: '1px solid #d9d9d9', borderRadius: 6 }} />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item name="window_end" label="结束时间" rules={[{ required: true }]}>
              <input type="time" style={{ width: '100%', height: 32, padding: '0 4px', border: '1px solid #d9d9d9', borderRadius: 6 }} />
            </Form.Item>
          </Col>
        </Row>

        <div style={{ marginTop: 4, marginBottom: 8, fontWeight: 500 }}>参与车辆</div>
        <Form.List name="vehicles">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name }) => (
                <Space key={key} style={{ display: 'flex', marginBottom: 4 }} align="baseline">
                  <Form.Item name={[name, 'enabled']} valuePropName="checked" noStyle><Checkbox /></Form.Item>
                  <Form.Item name={[name, 'vehicle_id']} noStyle><InputNumber placeholder="车辆ID" min={1} style={{ width: 90 }} /></Form.Item>
                  <Form.Item name={[name, 'current_soc']} noStyle><InputNumber placeholder="当前SOC" min={0} max={1} step={0.1} precision={2} style={{ width: 95 }} /></Form.Item>
                  <Form.Item name={[name, 'target_soc']} noStyle><InputNumber placeholder="目标SOC" min={0} max={1} step={0.1} precision={2} style={{ width: 95 }} /></Form.Item>
                  <Form.Item name={[name, 'max_power_kw']} noStyle><InputNumber placeholder="最大功率(kW)" min={0} step={0.5} style={{ width: 110 }} /></Form.Item>
                  <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#999' }} />
                </Space>
              ))}
              <Button type="dashed" onClick={() => add({ enabled: true, vehicle_id: fields.length + 1, current_soc: 0.3, target_soc: 0.9, max_power_kw: 7 })}
                icon={<PlusOutlined />} style={{ width: '100%' }}>
                添加车辆
              </Button>
            </>
          )}
        </Form.List>
      </Form>
    </Modal>
  );
};

export default GeneratePlanModal;
