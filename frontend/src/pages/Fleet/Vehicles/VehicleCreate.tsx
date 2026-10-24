/**
 * 车队 - 绑定新车 Modal
 *
 * 字段：车牌号(必填) / VIN码(必填) / 品牌 / 车型 / 绑定司机(Select)
 * 提交：POST /enterprises/{eid}/vehicles
 *
 * 说明：后端 VehicleBindRequest 实际接收 plate_number/vin/driver_name/driver_phone，
 *      品牌车型为前端扩展字段（后端暂不持久化），司机选择后自动映射出 name/phone。
 */
import React, { useEffect, useState } from 'react';
import { Modal, Form, Input, Select, Row, Col, message } from 'antd';
import { CarOutlined } from '@ant-design/icons';
import api from '../../../api';

export interface DriverOption {
  id: number;
  name: string;
  phone?: string;
}

interface VehicleCreateProps {
  open: boolean;
  enterpriseId: number | null;
  drivers: DriverOption[];
  onCancel: () => void;
  onSuccess: () => void;
}

const VehicleCreate: React.FC<VehicleCreateProps> = ({
  open, enterpriseId, drivers, onCancel, onSuccess,
}) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // 每次打开重置表单
  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleSubmit = async () => {
    if (!enterpriseId) {
      message.error('未选择企业，无法绑定');
      return;
    }
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      // 司机 id → 映射出后端需要的 driver_name/driver_phone
      const picked = drivers.find(d => d.id === values.driver_id);
      const payload = {
        plate_number: values.plate_number,
        vin: values.vin,
        brand: values.brand,
        model: values.model,
        driver_id: values.driver_id ?? undefined,
        driver_name: picked?.name,
        driver_phone: picked?.phone,
      };
      await api.post(`/enterprises/${enterpriseId}/vehicles`, payload);
      message.success('车辆绑定成功');
      onSuccess();
    } catch (err: any) {
      // 表单校验失败直接返回（antd Form 抛出带 errorFields 的对象）
      if (err?.errorFields) return;
      message.error('绑定失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="绑定新车"
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={submitting}
      width={560}
      destroyOnHidden
      okText="确定"
      cancelText="取消"
    >
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="plate_number" label="车牌号" rules={[{ required: true, message: '请输入车牌号' }]}>
              <Input prefix={<CarOutlined />} placeholder="如 京A·12345" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="vin" label="VIN码" tooltip="17位车辆识别代号" rules={[
              { required: true, message: '请输入VIN码' },
              { len: 17, message: 'VIN码必须为17位' },
            ]}>
              <Input placeholder="17位车架号" maxLength={17} style={{ fontWeight: 600, letterSpacing: 1 }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="brand" label="品牌">
              <Input placeholder="如 比亚迪" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="model" label="车型">
              <Input placeholder="如 T5" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="driver_id" label="绑定司机">
          <Select placeholder="选择司机（可选）" allowClear showSearch optionFilterProp="label">
            {drivers.map(d => (
              <Select.Option key={d.id} value={d.id} label={d.name}>
                {d.name}{d.phone ? ` (${d.phone})` : ''}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default VehicleCreate;
