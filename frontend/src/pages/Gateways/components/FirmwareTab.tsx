/**
 * 固件管理 Tab — 固件列表表格 + 上传入口
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Button, Space, Tag, Tooltip, Popconfirm, Alert, Empty, Spin, message, Modal, Form, Input,
} from 'antd';
import { CloudUploadOutlined, ReloadOutlined } from '@ant-design/icons';
import { fwStatusColorMap } from '../constants';
import { gatewayAPI } from '../../../api';
import type { Gateway } from '../../../types';

interface FirmwareTabProps {
  firmware: Gateway[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

const FirmwareTab: React.FC<FirmwareTabProps> = ({ firmware, loading, error, onRefresh }) => {
  const { t } = useTranslation();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [form] = Form.useForm();

  const doUpload = async () => {
    if (!file) { message.warning('请选择固件包文件'); return; }
    const v = await form.validateFields();
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('version', v.version);
      fd.append('model', v.model);
      fd.append('changelog', v.changelog || '');
      await gatewayAPI.uploadFirmware(fd);
      message.success(`固件 v${v.version} 已上传(draft), 发布后可用于升级`);
      setUploadOpen(false); setFile(null); form.resetFields();
      onRefresh();
    } catch (err: unknown) {
      message.error('上传失败: ' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    } finally { setUploading(false); }
  };

  const doRelease = async (id: number, ver: string) => {
    try {
      await gatewayAPI.releaseFirmware(id);
      message.success(`固件 v${ver} 已发布`);
      onRefresh();
    } catch (err: unknown) {
      message.error('发布失败: ' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    }
  };


  // 固件表格列
  const firmwareColumns = [
    {
      title: t('pages.gateways.version'),
      dataIndex: 'version',
      key: 'version',
      width: 120,
    },
    {
      title: t('pages.gateways.model'),
      dataIndex: 'model',
      key: 'model',
      width: 120,
    },
    {
      title: t('app.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={fwStatusColorMap[status] || 'default'}>
          {status === 'draft' ? t('pages.gateways.fw_draft') : status === 'released' ? t('pages.gateways.fw_released') : status === 'deprecated' ? t('pages.gateways.fw_deprecated') : status}
        </Tag>
      ),
    },
    {
      title: t('pages.gateways.file_size'),
      dataIndex: 'file_size',
      key: 'file_size',
      width: 120,
      render: (size: number) => size ? `${(size / 1024 / 1024).toFixed(2)} MB` : '-',
    },
    {
      title: t('pages.gateways.release_date'),
      dataIndex: 'release_date',
      key: 'release_date',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('app.action'),
      key: 'action',
      width: 160,
      render: (record: Gateway) => (
        <Space size="small">
          {record.status === 'draft' && (
            <Popconfirm title="确认发布此固件版本?" onConfirm={() => message.success('固件已发布')}>
              <Button size="small" type="primary">发布</Button>
            </Popconfirm>
          )}
          <Tooltip title="升级到此版本">
            <Button size="small" icon={<CloudUploadOutlined />} onClick={() => message.info('选择网关进行升级')}>
              升级
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} />}
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" icon={<CloudUploadOutlined />} onClick={() => setUploadOpen(true)}>
          上传固件
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      </Space>
      <Spin spinning={loading}>
        <div className="table-scroll-x">
        <Table
          dataSource={firmware}
          columns={firmwareColumns}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description={t('pages.gateways.fw_no_data')} /> }}
        />
        </div>
      </Spin>
      {/* 上传固件弹窗 */}
      <Modal title="上传固件" open={uploadOpen} onCancel={() => setUploadOpen(false)}
        onOk={doUpload} confirmLoading={uploading} okText="上传" destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="version" label="版本号" rules={[{ required: true, message: '必填, 如 V22.2.60' }]}>
            <Input placeholder="如 V22.2.60" />
          </Form.Item>
          <Form.Item name="model" label="适用型号" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 SDEE_DC_CHARGER / PWS1-450M" />
          </Form.Item>
          <Form.Item name="changelog" label="更新日志">
            <Input.TextArea rows={3} placeholder="本次更新内容" />
          </Form.Item>
          <Form.Item label="固件包(.bin)" required>
            <input type="file" accept=".bin,.hex,.img,.zip"
              onChange={(e) => setFile(e.target.files?.[0] || null)} />
            {file && <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>{file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)</div>}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default FirmwareTab;
