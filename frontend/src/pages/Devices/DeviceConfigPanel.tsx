/**
 * DeviceConfigPanel - 充电桩高级参数配置面板
 *
 * 该面板用于批量查看及修改充电桩的电压上限、电流上限、充电模式、
 * 时段电价以及过载保护阈值等参数。实现思路参考了已有的
 * `DeviceControlPanel`，使用 Ant Design 表单组件并通过 `deviceAPI`
 * 与后端 `/api/v1/devices/{id}/config` 接口交互。
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  Form,
  InputNumber,
  Select,
  Switch,
  Button,
  Space,
  Table,
  message,
  Spin,
  Input,
  Typography,
  Divider,
  Modal,
  Row,
  Col,
  Tag,
} from 'antd';
import { SettingOutlined, SaveOutlined, UndoOutlined, PlusOutlined, DeleteOutlined, CloudUploadOutlined, SafetyOutlined } from '@ant-design/icons';
import { deviceAPI } from '../../api';

const { Option } = Select;

interface TimePeriod {
  key: string;
  start_time: string;
  end_time: string;
  power_limit: number;
  price_per_kwh: number;
}

interface DeviceConfig {
  device_id: number;
  voltage_limit: number;
  current_limit: number;
  max_power: number;
  charge_mode: string;
  overload_protection: boolean;
  time_periods: TimePeriod[];
}

interface DeviceConfigPanelProps {
  deviceId: number;
  deviceName: string;
  open: boolean;
  onClose: () => void;
  onSave?: () => void;
}

const DeviceConfigPanel: React.FC<DeviceConfigPanelProps> = ({
  deviceId,
  deviceName,
  open,
  onClose,
  onSave,
}) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dispatching, setDispatching] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [timePeriods, setTimePeriods] = useState<TimePeriod[]>([]);

  useEffect(() => {
    if (open && deviceId) {
      fetchConfig();
    }
  }, [open, deviceId]);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const response = await deviceAPI.getConfig(deviceId);
      const config = response.data as DeviceConfig;
      
      // 设置表单值
      form.setFieldsValue({
        voltage_limit: config.voltage_limit,
        current_limit: config.current_limit,
        max_power: config.max_power,
        charge_mode: config.charge_mode,
        overload_protection: config.overload_protection,
      });
      
      // 处理时段配置
      const periodsWithKeys = (config.time_periods || []).map((p, index) => ({
        ...p,
        key: `period_${index}`,
      }));
      setTimePeriods(periodsWithKeys);
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.message || '获取配置失败';
      message.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      
      setSaving(true);
      try {
        const payload = {
          voltage_limit: values.voltage_limit,
          current_limit: values.current_limit,
          max_power: values.max_power,
          charge_mode: values.charge_mode,
          overload_protection: values.overload_protection,
          time_periods: timePeriods.map(({ key, ...rest }) => rest),
        };

        await deviceAPI.updateConfig(deviceId, payload);
        message.success('设备参数配置保存成功');
        onSave?.();
        onClose();
      } catch (err: any) {
        const errorMsg = err?.response?.data?.detail || err?.message || '保存配置失败';
        message.error(errorMsg);
      } finally {
        setSaving(false);
      }
    } catch {
      // 表单验证失败：静默处理（antd 已展示字段级错误提示）
    }
  };

  const handleDispatch = async () => {
    // 下发前先把屏幕上的最新值保存到平台，再推送到设备
    try {
      const values = await form.validateFields();
      setDispatching(true);
      try {
        const payload = {
          voltage_limit: values.voltage_limit,
          current_limit: values.current_limit,
          max_power: values.max_power,
          charge_mode: values.charge_mode,
          overload_protection: values.overload_protection,
          time_periods: timePeriods.map(({ key, ...rest }) => rest),
        };
        await deviceAPI.updateConfig(deviceId, payload);
        const res = await deviceAPI.dispatchConfig(deviceId);
        const data = res.data as any;
        const items: any[] = data?.items || [];
        const okCnt = items.filter((i) => String(i.result).startsWith('ok')).length;
        if (data?.dispatched) {
          message.success(`配置已下发到设备（${okCnt}/${items.length} 项成功）`);
        } else {
          message.warning(`配置下发（部分支持）：${items.map((i) => i.result).join('; ')}`);
        }
      } catch (err: any) {
        const errorMsg = err?.response?.data?.detail || err?.message || '下发失败';
        message.error(errorMsg);
      } finally {
        setDispatching(false);
      }
    } catch {
      message.warning('请先修正表单中的错误项再下发');
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const res = await deviceAPI.verifyConfig(deviceId);
      const data = res.data as any;
      setVerifyResult(data);
      if (data?.updated) {
        message.success('桩端定值已更新');
      } else {
        message.error(data?.message || '桩端定值未更新');
      }
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.message || '校验失败';
      message.error(errorMsg);
    } finally {
      setVerifying(false);
    }
  };

  const handleReset = async () => {
    Modal.confirm({
      title: '确认重置配置',
      content: '重置后将恢复为默认配置，确定继续吗？',
      onOk: async () => {
        try {
          await deviceAPI.updateConfig(deviceId, {
            voltage_limit: 420.0,
            current_limit: 60.0,
            max_power: 60.0,
            charge_mode: 'smart',
            overload_protection: true,
            time_periods: [],
          });
          message.success('配置已重置为默认值');
          form.resetFields();
          form.setFieldsValue({
            voltage_limit: 420.0,
            current_limit: 60.0,
            max_power: 60.0,
            charge_mode: 'smart',
            overload_protection: true,
          });
          setTimePeriods([]);
        } catch (err: any) {
          const errorMsg = err?.response?.data?.detail || err?.message || '重置配置失败';
          message.error(errorMsg);
        }
      },
    });
  };

  const addTimePeriod = () => {
    const newPeriod: TimePeriod = {
      key: `period_${Date.now()}`,
      start_time: '',
      end_time: '',
      power_limit: 30.0,
      price_per_kwh: 1.0,
    };
    setTimePeriods([...timePeriods, newPeriod]);
  };

  const removeTimePeriod = (key: string) => {
    setTimePeriods(timePeriods.filter(p => p.key !== key));
  };

  const updateTimePeriod = (key: string, field: string, value: any) => {
    setTimePeriods(timePeriods.map(p => 
      p.key === key ? { ...p, [field]: value } : p
    ));
  };

  const timePeriodColumns = [
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      render: (text: string, record: TimePeriod) => (
        <Input
          value={text}
          onChange={(e) => updateTimePeriod(record.key, 'start_time', e.target.value)}
          placeholder="HH:MM"
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: '结束时间',
      dataIndex: 'end_time',
      key: 'end_time',
      render: (text: string, record: TimePeriod) => (
        <Input
          value={text}
          onChange={(e) => updateTimePeriod(record.key, 'end_time', e.target.value)}
          placeholder="HH:MM"
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: '功率限制(kW)',
      dataIndex: 'power_limit',
      key: 'power_limit',
      render: (value: number, record: TimePeriod) => (
        <InputNumber
          value={value}
          onChange={(val) => updateTimePeriod(record.key, 'power_limit', val)}
          min={0}
          max={1000}
          step={0.1}
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: '电价(元/kWh)',
      dataIndex: 'price_per_kwh',
      key: 'price_per_kwh',
      render: (value: number, record: TimePeriod) => (
        <InputNumber
          value={value}
          onChange={(val) => updateTimePeriod(record.key, 'price_per_kwh', val)}
          min={0}
          max={10}
          step={0.01}
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: TimePeriod) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => removeTimePeriod(record.key)}
        >
          删除
        </Button>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <SettingOutlined />
          <span>参数配置 - {deviceName}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      width={700}
      okText="保存"
      cancelText="取消"
      okButtonProps={{ loading: saving, icon: <SaveOutlined /> }}
      footer={[
        <Button key="cancel" onClick={onClose}>取消</Button>,
        <Button key="dispatch" type="primary" ghost icon={<CloudUploadOutlined />} loading={dispatching} onClick={handleDispatch}>
          下发
        </Button>,
        <Button key="verify" icon={<SafetyOutlined />} loading={verifying} onClick={handleVerify}>
          校验
        </Button>,
        <Button key="save" type="primary" loading={saving} icon={<SaveOutlined />} onClick={handleSave}>
          保存
        </Button>,
      ]}
    >
      <Spin spinning={loading}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="voltage_limit"
                label="电压上限(V)"
                rules={[{ required: true, message: '请输入电压上限' }]}
              >
                <InputNumber
                  min={200}
                  max={750}
                  step={1}
                  style={{ width: '100%' }}
                  placeholder="420"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="current_limit"
                label="电流上限(A)"
                rules={[{ required: true, message: '请输入电流上限' }]}
              >
                <InputNumber
                  min={0}
                  max={200}
                  step={1}
                  style={{ width: '100%' }}
                  placeholder="60"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="max_power"
                label="最大功率(kW)"
                rules={[{ required: true, message: '请输入最大功率' }]}
              >
                <InputNumber
                  min={0}
                  max={200}
                  step={0.1}
                  style={{ width: '100%' }}
                  placeholder="60"
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="charge_mode"
                label="充电模式"
                rules={[{ required: true, message: '请选择充电模式' }]}
              >
                <Select>
                  <Option value="fast">快充</Option>
                  <Option value="smart">智能</Option>
                  <Option value="eco">经济</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="overload_protection"
                label="过载保护"
                valuePropName="checked"
              >
                <Switch checkedChildren="启用" unCheckedChildren="禁用" />
              </Form.Item>
            </Col>
          </Row>

          <Divider>时段电价配置</Divider>
          
          <Space style={{ marginBottom: 16 }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={addTimePeriod}
            >
              添加时段
            </Button>
          </Space>

          <Table
            dataSource={timePeriods}
            columns={timePeriodColumns}
            rowKey="key"
            size="small"
            pagination={false}
            locale={{ emptyText: '暂无时段配置' }}
          />
        </Form>
      </Spin>

      {/* 校验结果弹窗 (2026-10-09 丁哥: 读桩上传数据比对下发定值) */}
      <Modal
        title={
          <Space>
            <SafetyOutlined />
            <span>配置校验 - {deviceName}</span>
            {verifyResult && (
              <Tag color={verifyResult.updated ? 'success' : 'error'}>
                {verifyResult.updated ? '✓ 桩端定值已更新' : '✗ 桩端定值未更新'}
              </Tag>
            )}
          </Space>
        }
        open={!!verifyResult}
        onCancel={() => setVerifyResult(null)}
        footer={<Button type="primary" onClick={() => setVerifyResult(null)}>知道了</Button>}
        width={620}
      >
        <Table
          scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
          size="small"
          rowKey={(r: any) => r.item}
          dataSource={verifyResult?.items || []}
          pagination={false}
          columns={[
            { title: '校验项', dataIndex: 'item', width: 140 },
            { title: '期望', dataIndex: 'expected', width: 120 },
            { title: '实际', dataIndex: 'actual', width: 140 },
            {
              title: '结果', dataIndex: 'ok', width: 100,
              render: (v: boolean | null) =>
                v === true ? <Tag color="success">✓ 通过</Tag> :
                v === false ? <Tag color="error">✗ 异常</Tag> :
                <Tag color="default">待确认</Tag>,
            },
          ]}
        />
      </Modal>
    </Modal>
  );
};

export default DeviceConfigPanel;