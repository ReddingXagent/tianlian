/**
 * 固件升级 Modal — 设备 OTA 升级（任务清单：设备管理 → 固件升级 / spec 2.4 设备控制）
 * 展示当前固件版本，下发目标版本升级任务；升级为异步任务，提交后由后端执行。
 */
import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Button, message, Descriptions, Switch, Select } from 'antd';
import { UpCircleOutlined } from '@ant-design/icons';
import { deviceAPI, gatewayAPI } from '../../../api';

interface FirmwareDevice {
  id: number;
  name?: string;
  sn?: string;
  model?: string;
  firmware_version?: string;
}

interface FirmwareUpgradeModalProps {
  open: boolean;
  device: FirmwareDevice | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const FirmwareUpgradeModal: React.FC<FirmwareUpgradeModalProps> = ({ open, device, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [fwOptions, setFwOptions] = useState<{label: string; value: string; url?: string}[]>([]);
  const [currentVersion, setCurrentVersion] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    setCurrentVersion(device?.firmware_version ?? '');
    form.resetFields();
  }, [open, device, form]);

  useEffect(() => {
    if (!open) return;
    gatewayAPI.firmware().then((res: any) => {
      const items = res.data?.data || res.data?.items || res.data || [];
      const opts = (Array.isArray(items) ? items : [])
        .filter((f: any) => f.status === 'released')
        .map((f: any) => ({ label: `${f.version} (${f.model})`, value: f.version, url: `/api/v1/gateways/firmware/${f.id}/download` }));
      setFwOptions(opts);
    }).catch((err: any) => {
      message.error('加载固件版本列表失败：' + (err?.response?.data?.detail || err?.message));
      setFwOptions([]);
    });
  }, [open]);

  const handleSubmit = async (values: { target_version: string; url?: string; force?: boolean }) => {
    if (!device) return;
    setSubmitting(true);
    try {
      await deviceAPI.firmware.upgrade(device.id, {
        target_version: values.target_version,
        url: values.url || undefined,
        force: values.force ?? false,
      });
      message.success(`固件升级任务已下发（目标版本 ${values.target_version}）`);
      form.resetFields();
      onSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error('升级失败:' + (error?.response?.data?.detail || error?.message));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={(<><UpCircleOutlined /> 固件升级</>)}
      open={open}
      onCancel={() => { form.resetFields(); onCancel(); }}
      footer={null}
      destroyOnHidden
    >
      <Descriptions size="small" column={1} bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="设备">{device ? `${device.name ?? ''}（${device.sn ?? '-'}）` : '-'}</Descriptions.Item>
        <Descriptions.Item label="型号">{device?.model || '—'}</Descriptions.Item>
        <Descriptions.Item label="当前固件版本">{currentVersion || '—'}</Descriptions.Item>
      </Descriptions>
      <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ force: false }}>
        <Form.Item
          name="target_version"
          label="目标固件版本(固件库released)"
          rules={[{ required: true, message: '请选择目标固件版本' }]}
        >
          <Select
            placeholder={fwOptions.length ? '从已发布固件选择' : '固件库暂无已发布固件(网关管理-固件Tab上传发布)'}
            options={fwOptions}
            showSearch
            optionFilterProp="label"
            onChange={(_: unknown, opt: any) => { if (opt?.url) form.setFieldValue('url', opt.url); }}
          />
        </Form.Item>
        <Form.Item name="url" label="固件包地址（可选, 选版本自动填充）">
          <Input placeholder="https://.../firmware.bin" />
        </Form.Item>
        <Form.Item name="force" label="强制升级" valuePropName="checked" tooltip="跳过版本一致性校验，强制下发升级">
          <Switch checkedChildren="开" unCheckedChildren="关" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block icon={<UpCircleOutlined />} loading={submitting}>
          下发升级任务
        </Button>
      </Form>
    </Modal>
  );
};

export default FirmwareUpgradeModal;
