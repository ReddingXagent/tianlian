/**
 * 到场签到 Modal — 工单生命周期「到场」环节（spec 2.2）
 * 工程师到达现场后打卡：GPS 定位 + 地址 + 备注，记录到场时间。
 * 定位依赖浏览器 geolocation，不可用时降级为手动输入。
 */
import React, { useState } from 'react';
import { Modal, Form, Input, Button, message, Descriptions, Row, Col } from 'antd';
import { EnvironmentOutlined, AimOutlined } from '@ant-design/icons';
import { workorderAPI } from '../../../api';

const { TextArea } = Input;

interface CheckInModalProps {
  open: boolean;
  orderId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

interface Position {
  latitude?: number;
  longitude?: number;
}

const CheckInModal: React.FC<CheckInModalProps> = ({ open, orderId, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [locating, setLocating] = useState(false);
  const [position, setPosition] = useState<Position>({});

  // 获取 GPS 定位（浏览器 API，失败静默降级为手动输入）
  const handleLocate = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      message.warning('当前环境不支持定位，请手动输入经纬度');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        setPosition({ latitude, longitude });
        form.setFieldsValue({ latitude, longitude });
        setLocating(false);
        message.success('定位成功');
      },
      () => {
        setLocating(false);
        message.warning('定位失败，请手动输入经纬度');
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 },
    );
  };

  const handleSubmit = async (values: {
    latitude?: number;
    longitude?: number;
    address?: string;
    note?: string;
  }) => {
    setSubmitting(true);
    try {
      await workorderAPI.checkin(orderId, {
        latitude: values.latitude != null ? Number(values.latitude) : undefined,
        longitude: values.longitude != null ? Number(values.longitude) : undefined,
        address: values.address,
        note: values.note,
      });
      message.success('到场签到成功');
      form.resetFields();
      setPosition({});
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('签到失败:' + (error?.response?.data?.detail || error?.message));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={(<><EnvironmentOutlined /> 到场签到</>)}
      open={open}
      onCancel={() => { form.resetFields(); setPosition({}); onCancel(); }}
      footer={null}
      destroyOnHidden
    >
      <div style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<AimOutlined />} loading={locating} onClick={handleLocate}>
          获取当前位置
        </Button>
        {position.latitude != null && (
          <Descriptions size="small" column={2} style={{ marginTop: 12 }}>
            <Descriptions.Item label="纬度">{position.latitude?.toFixed(6)}</Descriptions.Item>
            <Descriptions.Item label="经度">{position.longitude?.toFixed(6)}</Descriptions.Item>
          </Descriptions>
        )}
      </div>
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        <Row gutter={8}>
          <Col span={12}>
            <Form.Item name="latitude" label="纬度">
              <Input type="number" placeholder="如 31.2304" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="longitude" label="经度">
              <Input type="number" placeholder="如 121.4737" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="address" label="到场地址">
          <Input placeholder="请输入或确认到场地址" />
        </Form.Item>
        <Form.Item name="note" label="签到备注">
          <TextArea rows={2} placeholder="现场情况说明（可选）" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting}>
          确认签到
        </Button>
      </Form>
    </Modal>
  );
};

export default CheckInModal;
