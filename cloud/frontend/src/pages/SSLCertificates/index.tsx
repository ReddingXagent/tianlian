/**
 * SSL证书管理页面
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Tag, Space, message,
  Tabs, Row, Col, Statistic, Descriptions, Switch, InputNumber, Popconfirm, Alert, Progress
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  SafetyCertificateOutlined, PlusOutlined, SyncOutlined, DeleteOutlined,
  SettingOutlined, AlertOutlined, CheckCircleOutlined, ClockCircleOutlined
} from '@ant-design/icons';
import api from '../../api';

interface SSLCertificate {
  id: number;
  domain: string;
  email: string;
  status: string;
  issuer?: string;
  not_before?: string;
  not_after?: string;
  days_remaining?: number;
  subject_alt_names?: string[];
  auto_renew: boolean;
  renew_days_before: number;
  cert_path?: string;
  key_path?: string;
  last_renew_at?: string;
  last_renew_success?: boolean;
  last_renew_error?: string;
  last_check_at?: string;
  created_at: string;
}

const SSLCertificatesPage: React.FC = () => {
  const [certs, setCerts] = useState<SSLCertificate[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [renewModalVisible, setRenewModalVisible] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);
  const [selectedCert, setSelectedCert] = useState<SSLCertificate | null>(null);
  const [healthStats, setHealthStats] = useState<any>(null);
  const [form] = Form.useForm();
  const [renewForm] = Form.useForm();
  const [configForm] = Form.useForm();

  const fetchCerts = async () => {
    setLoading(true);
    try {
      const res = await api.get('/ssl/certificates');
      const data = res.data as any;
      setCerts(data.certificates || data || []);
    } catch (error) {
      message.error('获取证书列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchHealth = async () => {
    try {
      const res = await api.get('/ssl/health-check');
      setHealthStats(res.data);
    } catch (error) {
      // ignore
    }
  };

  useEffect(() => {
    fetchCerts();
    fetchHealth();
  }, []);

  const handleCreate = async (values: any) => {
    try {
      await api.post('/ssl/certificates', {
        domain: values.domain,
        email: values.email,
        sans: values.sans?.split(',').map(s => s.trim()).filter(s => s) || [],
        auto_renew: values.auto_renew,
        renew_days_before: values.renew_days_before,
      });
      message.success('证书申请已启动，请等待完成');
      setCreateModalVisible(false);
      form.resetFields();
      fetchCerts();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '申请失败');
    }
  };

  const handleRenew = async (values: any) => {
    if (!selectedCert) return;
    try {
      await api.post(`/ssl/certificates/${selectedCert.domain}/renew`, { staging: values.staging });
      message.success('续期已启动');
      setRenewModalVisible(false);
      renewForm.resetFields();
      fetchCerts();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '续期失败');
    }
  };

  const handleUpdateConfig = async (values: any) => {
    if (!selectedCert) return;
    try {
      await api.put(`/ssl/certificates/${selectedCert.domain}/config`, values);
      message.success('配置已更新');
      setConfigModalVisible(false);
      configForm.resetFields();
      fetchCerts();
    } catch (error) {
      message.error('更新失败');
    }
  };

  const handleDelete = async (domain: string) => {
    try {
      await api.delete(`/ssl/certificates/${domain}`);
      message.success('证书记录已删除');
      fetchCerts();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleAutoRenew = async () => {
    try {
      const res = await api.post('/ssl/auto-renew');
      const data = res.data as any;
      message.success(`已触发 ${data.needs_renewal || 0} 个证书续期`);
      fetchCerts();
    } catch (error) {
      message.error('触发失败');
    }
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      active: { color: 'green', text: '有效' },
      expiring_soon: { color: 'orange', text: '即将过期' },
      expired: { color: 'red', text: '已过期' },
      pending: { color: 'blue', text: '申请中' },
      error: { color: 'red', text: '异常' },
    };
    return map[status] || { color: 'default', text: status };
  };

  const getDaysRemainingTag = (days?: number, renewDays?: number) => {
    if (!days) return <Tag>未知</Tag>;
    if (days <= 0) return <Tag color="red">已过期</Tag>;
    if (days <= (renewDays || 30)) return <Tag color="orange">{days}天</Tag>;
    return <Tag color="green">{days}天</Tag>;
  };

  const columns: ColumnsType<SSLCertificate> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '域名', dataIndex: 'domain', width: 200 },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => {
      const t = getStatusTag(v);
      return <Tag color={t.color}>{t.text}</Tag>;
    }},
    { title: '剩余天数', dataIndex: 'days_remaining', width: 120, render: (v: number | undefined, r: SSLCertificate) => (
      <Space>
        {getDaysRemainingTag(v, r.renew_days_before)}
        {v !== undefined && <Progress percent={Math.min(100, (v / 365) * 100)} size="small" showInfo={false} />}
      </Space>
    )},
    { title: '过期时间', dataIndex: 'not_after', width: 160, render: (v: string) => v?.slice(0, 10) || '-' },
    { title: '自动续期', dataIndex: 'auto_renew', width: 100, render: (v: boolean) => (
      <Tag color={v ? 'green' : 'default'}>{v ? '开启' : '关闭'}</Tag>
    )},
    { title: '提前续期天数', dataIndex: 'renew_days_before', width: 120 },
    { title: '最后续期', dataIndex: 'last_renew_at', width: 160, render: (v: string) => v?.slice(0, 19) || '-' },
    { title: '续期状态', dataIndex: 'last_renew_success', width: 100, render: (v?: boolean) => (
      v === true ? <Tag color="green">成功</Tag> :
      v === false ? <Tag color="red">失败</Tag> : <Tag>-</Tag>
    )},
    { title: '操作', width: 180, fixed: 'right', render: (_: any, r: SSLCertificate) => (
      <Space size="small">
        <Button size="small" icon={<SyncOutlined />} onClick={() => { setSelectedCert(r); setRenewModalVisible(true); }}>续期</Button>
        <Button size="small" icon={<SettingOutlined />} onClick={() => { setSelectedCert(r); configForm.setFieldsValue({ auto_renew: r.auto_renew, renew_days_before: r.renew_days_before }); setConfigModalVisible(true); }}>配置</Button>
        <Popconfirm title="确认删除证书记录？" onConfirm={() => handleDelete(r.domain)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <Card title={<><SafetyCertificateOutlined /> SSL证书管理</>} extra={
      <Space>
        <Button icon={<SyncOutlined />} onClick={handleAutoRenew}>自动续期检查</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>申请证书</Button>
      </Space>
    }>
      <Tabs items={[
        {
          key: 'certificates',
          label: '证书列表',
          children: (
            <>
              {healthStats && (
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={4}><Statistic title="总证书数" value={healthStats.total || 0} /></Col>
                  <Col span={4}><Statistic title="健康" value={healthStats.healthy || 0} valueStyle={{ color: '#3f8600' }} /></Col>
                  <Col span={4}><Statistic title="即将过期" value={healthStats.expiring_soon || 0} valueStyle={{ color: '#fa8c16' }} /></Col>
                  <Col span={4}><Statistic title="已过期" value={healthStats.expired || 0} valueStyle={{ color: '#cf1322' }} /></Col>
                </Row>
              )}
              {healthStats?.expired > 0 && (
                <Alert type="error" message={`有 ${healthStats.expired} 个证书已过期，请立即处理！`} style={{ marginBottom: 16 }} />
              )}
              {healthStats?.expiring_soon > 0 && (
                <Alert type="warning" message={`有 ${healthStats.expiring_soon} 个证书即将过期（30天内）`} style={{ marginBottom: 16 }} />
              )}
              <Table dataSource={certs} columns={columns} rowKey="id" loading={loading} scroll={{ x: 1200 }} />
            </>
          ),
        },
        {
          key: 'expiring',
          label: '即将过期',
          children: (
            <Table dataSource={certs.filter(c => c.status === 'expiring_soon' || c.status === 'expired')} columns={columns} rowKey="id" />
          ),
        },
      ]} />

      {/* 申请证书弹窗 */}
      <Modal title="申请SSL证书" open={createModalVisible} onCancel={() => setCreateModalVisible(false)} footer={null} width={600}>
        <Alert type="info" message="使用 Let's Encrypt 自动申请免费SSL证书" style={{ marginBottom: 16 }} />
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="domain" label="主域名" rules={[{ required: true, message: '请输入域名' }]}>
            <Input placeholder="example.com" />
          </Form.Item>
          <Form.Item name="sans" label="SAN域名（多个用逗号分隔）">
            <Input placeholder="www.example.com, api.example.com" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" initialValue="admin@tianlian.com">
            <Input placeholder="Let's Encrypt 注册邮箱" />
          </Form.Item>
          <Form.Item name="auto_renew" label="自动续期" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item name="renew_days_before" label="提前续期天数" initialValue={30}>
            <InputNumber min={1} max={60} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>提交申请</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 手动续期弹窗 */}
      <Modal title="手动续期证书" open={renewModalVisible} onCancel={() => setRenewModalVisible(false)} footer={null}>
        {selectedCert && (
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="域名">{selectedCert.domain}</Descriptions.Item>
            <Descriptions.Item label="剩余天数">{selectedCert.days_remaining || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">{getStatusTag(selectedCert.status).text}</Descriptions.Item>
          </Descriptions>
        )}
        <Form form={renewForm} onFinish={handleRenew} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="staging" label="测试模式" valuePropName="checked" initialValue={false}>
            <Switch checkedChildren="测试" unCheckedChildren="正式" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block icon={<SyncOutlined />}>开始续期</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 配置弹窗 */}
      <Modal title="证书配置" open={configModalVisible} onCancel={() => setConfigModalVisible(false)} footer={null}>
        {selectedCert && (
          <Descriptions bordered size="small" column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="域名">{selectedCert.domain}</Descriptions.Item>
          </Descriptions>
        )}
        <Form form={configForm} onFinish={handleUpdateConfig} layout="vertical">
          <Form.Item name="auto_renew" label="自动续期" valuePropName="checked">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item name="renew_days_before" label="提前续期天数">
            <InputNumber min={1} max={60} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>保存配置</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 说明卡片 */}
      <Card size="small" title="说明" style={{ marginTop: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="证书来源">Let's Encrypt 自动签发（免费）</Descriptions.Item>
          <Descriptions.Item label="自动续期">开启后将在过期前N天自动续期</Descriptions.Item>
          <Descriptions.Item label="过期处理">已过期证书需手动续期或重新申请</Descriptions.Item>
        </Descriptions>
      </Card>
    </Card>
  );
};

export default SSLCertificatesPage;