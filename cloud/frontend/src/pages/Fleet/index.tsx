/**
 * 天链 V3 - 车队管理页面
 *
 * Tab：车队企业 / 车辆管理 / 资金账户 / 司机管理 / 碳排放 / 智能充电调度 / 费用结算等（纯用户团体，不涉场站运维）
 * 车辆管理 Tab 由独立子模块 FleetVehiclesPage 承载（企业维度 CRUD + 详情/状态变更）。
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message, Alert,
  Popconfirm, Statistic, Row, Col, Tabs, InputNumber,
} from 'antd';
import {
  DashboardOutlined, PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SearchOutlined, TeamOutlined, CarOutlined, DollarOutlined,
  IdcardOutlined, BankOutlined,
  ExperimentOutlined, CalendarOutlined, FileTextOutlined,
  ScheduleOutlined, SettingOutlined,
  SlidersOutlined, FileProtectOutlined, ToolOutlined,
  SafetyOutlined, FundOutlined,
} from '@ant-design/icons';
import api from '../../api';
import PageWrapper from '../../components/PageWrapper';
import { useIsMobile } from '../../hooks/useIsMobile';

// 子模块
import FleetDashboardPage from './Dashboard';
import FleetDriversPage from './Drivers';
import FleetCarbonPage from './Carbon';
import FleetSettlementPage from './Settlement';
import FleetRechargePage from './Recharge';
import FleetChargingSchedulePage from './ChargingSchedule';
import FleetVehiclesPage from './Vehicles';
import FleetChargingPoliciesPage from './ChargingPolicies';
import FleetAttendancePage from './Attendance';
import FleetCarbonCertificatesPage from './CarbonCertificates';
import FleetVehicleMaintenancePage from './VehicleMaintenance';
import FleetVehicleInsurancePage from './VehicleInsurance';
import FleetChargingStatsPage from './ChargingStats';
import FleetSettingsPage from './Settings';

/* ── 类型定义 ── */
interface Enterprise {
  id: number;
  name: string;
  code: string;
  contact?: string;
  phone?: string;
  address?: string;
  vehicle_count?: number;
  driver_count?: number;
  status: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

interface FundAccount {
  id: number;
  enterprise_id?: number;
  enterprise_name?: string;
  account_name: string;
  account_type: string;
  balance: number;
  status: string;
  bank_name?: string;
  bank_account?: string;
  currency?: string;
  description?: string;
  created_at?: string;
}

/* ── 常量 ── */
const TAG_COLORS: Record<string, string> = {
  active: 'green', normal: 'green', online: 'green', 启用: 'green', 正常: 'green',
  maintenance: 'orange', warning: 'orange', pending: 'orange', 维护: 'orange',
  inactive: 'red', closed: 'red', offline: 'red', frozen: 'red', 停用: 'red', 冻结: 'red',
};

const STATUS_TEXT: Record<string, string> = {
  active: '启用', normal: '正常', online: '在线',
  maintenance: '维护中', warning: '预警', pending: '待处理',
  inactive: '停用', closed: '已关闭', offline: '离线', frozen: '已冻结',
};

const FUND_TYPES = ['运营账户', '维修基金', '备用金', '保证金', '结算账户'];

/* ── 主页面组件（企业 / 资金 内联 + 车辆/司机等子模块Tab） ── */
const FleetPage: React.FC = () => {
  // activeTab 以 URL ?tab=xxx 为单一数据源, 与左侧菜单 navigate('/fleet?tab=xxx') 双向同步:
  //   菜单点击 → URL 变 → activeTab 重算;  页面内切 tab → 写回 URL (供刷新/分享/菜单联动)
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'enterprises';
  // 移动端 Modal 自适应宽度（桌面固定 560，移动端近全屏）
  const isMobile = useIsMobile();
  const modalWidth = isMobile ? 'calc(100vw - 24px)' : 560;
  const handleTabChange = useCallback((key: string) => {
    // 默认 enterprises 不写 query, 保持 /fleet 干净
    setSearchParams(key && key !== 'enterprises' ? { tab: key } : {});
  }, [setSearchParams]);

  // 企业
  const [enterprises, setEnterprises] = useState<Enterprise[]>([]);
  const [enterpriseLoading, setEnterpriseLoading] = useState(false);
  const [enterpriseSearch, setEnterpriseSearch] = useState('');

  // 资金
  const [fundAccounts, setFundAccounts] = useState<FundAccount[]>([]);
  const [fundLoading, setFundLoading] = useState(false);
  const [fundSearch, setFundSearch] = useState('');

  // 加载失败态（企业/资金各自独立）：失败时渲染错误提示+重试，绝不回退假数据
  const [enterpriseError, setEnterpriseError] = useState<string | null>(null);
  const [fundError, setFundError] = useState<string | null>(null);

  // Modal
  const [enterpriseModalOpen, setEnterpriseModalOpen] = useState(false);
  const [fundModalOpen, setFundModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [enterpriseForm] = Form.useForm();
  const [fundForm] = Form.useForm();

  /* ── 数据加载 ── */
  const loadEnterprises = useCallback(async () => {
    setEnterpriseLoading(true);
    setEnterpriseError(null);
    try {
      const { data } = await api.get('/fleet/enterprises');
      setEnterprises(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch (err: any) {
      setEnterprises([]);
      const text = err?.response?.data?.message || err?.response?.data?.detail || err?.message || '加载失败';
      setEnterpriseError(text);
      message.error('车队企业加载失败：' + text);
    } finally {
      setEnterpriseLoading(false);
    }
  }, []);

  const loadFunds = useCallback(async () => {
    setFundLoading(true);
    setFundError(null);
    try {
      const { data } = await api.get('/fleet/funds');
      setFundAccounts(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch (err: any) {
      setFundAccounts([]);
      const text = err?.response?.data?.message || err?.response?.data?.detail || err?.message || '加载失败';
      setFundError(text);
      message.error('资金账户加载失败：' + text);
    } finally {
      setFundLoading(false);
    }
  }, []);

  useEffect(() => { loadEnterprises(); loadFunds(); }, [loadEnterprises, loadFunds]);

  const refreshTab = () => {
    if (activeTab === 'enterprises') loadEnterprises();
    else loadFunds();
  };

  /* ── 车队企业 CRUD ── */
  const handleEnterpriseSubmit = async () => {
    try {
      const values = await enterpriseForm.validateFields();
      if (editingItem) {
        await api.put(`/fleet/enterprises/${editingItem.id}`, values);
        message.success('车队企业已更新');
      } else {
        await api.post('/fleet/enterprises', values);
        message.success('车队企业已创建');
      }
      setEnterpriseModalOpen(false);
      enterpriseForm.resetFields();
      setEditingItem(null);
      loadEnterprises();
    } catch (err: any) {
      if ((err as any)?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDeleteEnterprise = async (id: number) => {
    try {
      await api.delete(`/fleet/enterprises/${id}`);
      message.success('已删除');
      loadEnterprises();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 资金 CRUD ── */
  const handleFundSubmit = async () => {
    try {
      const values = await fundForm.validateFields();
      if (editingItem) {
        await api.put(`/fleet/funds/${editingItem.id}`, values);
        message.success('资金账户已更新');
      } else {
        await api.post('/fleet/funds', values);
        message.success('资金账户已创建');
      }
      setFundModalOpen(false);
      fundForm.resetFields();
      setEditingItem(null);
      loadFunds();
    } catch (err: any) {
      if ((err as any)?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDeleteFund = async (id: number) => {
    try {
      await api.delete(`/fleet/funds/${id}`);
      message.success('已删除');
      loadFunds();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 筛选 ── */
  const filteredEnterprises = enterprises.filter(
    e => !enterpriseSearch || e.name?.toLowerCase().includes(enterpriseSearch.toLowerCase()) || e.code?.toLowerCase().includes(enterpriseSearch.toLowerCase())
  );
  const filteredFunds = fundAccounts.filter(
    f => !fundSearch || f.account_name?.toLowerCase().includes(fundSearch.toLowerCase()) || f.enterprise_name?.toLowerCase().includes(fundSearch.toLowerCase())
  );

  /* ── 统计 ── */
  const enterpriseStats = {
    total: enterprises.length,
    active: enterprises.filter(e => e.status === 'active' || e.status === 'normal').length,
    totalVehicles: enterprises.reduce((s, e) => s + (e.vehicle_count || 0), 0),
    totalDrivers: enterprises.reduce((s, e) => s + (e.driver_count || 0), 0),
  };

  const fundStats = {
    total: fundAccounts.length,
    totalBalance: fundAccounts.reduce((s, f) => s + (f.balance || 0), 0),
    active: fundAccounts.filter(f => f.status === 'active' || f.status === 'normal').length,
    frozen: fundAccounts.filter(f => f.status === 'frozen').length,
  };

  /* ── 辅助函数 ── */
  const statusColor = (s: string) => TAG_COLORS[s] || 'default';
  const statusLabel = (s: string) => STATUS_TEXT[s] || s;

  /* ── 车队企业列 ── */
  const enterpriseColumns = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 100, render: (c: string) => c ? <Tag color="blue">{c}</Tag> : '-' },
    { title: '企业名称', dataIndex: 'name', key: 'name', width: 160 },
    { title: '联系人', dataIndex: 'contact', key: 'contact', width: 90 },
    { title: '联系电话', dataIndex: 'phone', key: 'phone', width: 120, render: (p: string) => p || '-' },
    { title: '地址', dataIndex: 'address', key: 'address', ellipsis: true },
    { title: '车辆数', dataIndex: 'vehicle_count', key: 'vehicle_count', width: 80, align: 'right' as const },
    { title: '司机数', dataIndex: 'driver_count', key: 'driver_count', width: 80, align: 'right' as const },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag> },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: Enterprise) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            enterpriseForm.setFieldsValue(record);
            setEnterpriseModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteEnterprise(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /* ── 资金账户列 ── */
  const fundColumns = [
    { title: '账户名称', dataIndex: 'account_name', key: 'account_name', width: 140 },
    { title: '所属企业', dataIndex: 'enterprise_name', key: 'enterprise_name', width: 140, ellipsis: true },
    { title: '账户类型', dataIndex: 'account_type', key: 'account_type', width: 100, render: (v: string) => v ? <Tag color="purple">{v}</Tag> : '-' },
    { title: '余额', dataIndex: 'balance', key: 'balance', width: 130, align: 'right' as const,
      render: (v: number, r: FundAccount) => (
        <span style={{ fontWeight: 600, color: v > 0 ? '#34a853' : v < 0 ? '#ea4335' : '#999' }}>
          {r.currency || '¥'} {v != null ? v.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}
        </span>
      ),
    },
    { title: '开户银行', dataIndex: 'bank_name', key: 'bank_name', width: 120, ellipsis: true },
    { title: '银行账号', dataIndex: 'bank_account', key: 'bank_account', width: 160, render: (v: string) => v ? <code style={{ fontSize: 11 }}>{v}</code> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag> },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: FundAccount) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            fundForm.setFieldsValue(record);
            setFundModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteFund(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /* ── 当前Tab数据 ── */
  const currentLoading = activeTab === 'enterprises' ? enterpriseLoading : fundLoading;
  const currentEmpty = activeTab === 'enterprises' ? enterprises.length === 0 : fundAccounts.length === 0;

  const openAddModal = () => {
    setEditingItem(null);
    if (activeTab === 'enterprises') {
      enterpriseForm.resetFields();
      enterpriseForm.setFieldsValue({ status: 'active' });
      setEnterpriseModalOpen(true);
    } else {
      fundForm.resetFields();
      fundForm.setFieldsValue({ status: 'active', currency: '¥', balance: 0 });
      setFundModalOpen(true);
    }
  };

  // 子模块 Tab（自包含，不显示外层工具条）
  const isSubModule = ['dashboard', 'vehicles', 'drivers', 'carbon', 'settlement', 'settings', 'policies', 'attendance', 'carbon-cert', 'maintenance', 'insurance', 'charging-stats', 'recharge'].includes(activeTab);

  return (
    <PageWrapper
      loading={currentLoading && currentEmpty && !isSubModule}
      skeletonType="table"
      skeletonCount={6}
      hasData={isSubModule || !currentEmpty}
      transition="slide-up"
    >
      <div className="page-container">
        {/* 统计卡片 - 仅企业/资金Tab显示 */}
        {activeTab === 'enterprises' && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}>
              <Card><Statistic title="企业总数" value={enterpriseStats.total} prefix={<TeamOutlined />} /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="活跃企业" value={enterpriseStats.active} valueStyle={{ color: '#34a853' }} /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="车辆总数" value={enterpriseStats.totalVehicles} prefix={<CarOutlined />} /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="司机总数" value={enterpriseStats.totalDrivers} prefix={<IdcardOutlined />} /></Card>
            </Col>
          </Row>
        )}
        {activeTab === 'funds' && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}><Card><Statistic title="账户总数" value={fundStats.total} prefix={<BankOutlined />} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="正常账户" value={fundStats.active} valueStyle={{ color: '#34a853' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="冻结账户" value={fundStats.frozen} valueStyle={{ color: '#ea4335' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="总余额" value={fundStats.totalBalance} precision={2} prefix="¥" valueStyle={{ color: fundStats.totalBalance >= 0 ? '#34a853' : '#ea4335' }} /></Card></Col>
          </Row>
        )}

        {/* Tab 切换 */}
        <Card
          extra={!isSubModule ? (
            <Space>
              {activeTab === 'enterprises' && (
                <Input placeholder="搜索企业名称/编码" prefix={<SearchOutlined />} value={enterpriseSearch} onChange={e => setEnterpriseSearch(e.target.value)} style={{ width: 200 }} allowClear />
              )}
              {activeTab === 'funds' && (
                <Input placeholder="搜索账户/企业" prefix={<SearchOutlined />} value={fundSearch} onChange={e => setFundSearch(e.target.value)} style={{ width: 200 }} allowClear />
              )}
              <Button icon={<ReloadOutlined />} onClick={refreshTab}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
                {activeTab === 'enterprises' ? '新增企业' : '新增账户'}
              </Button>
            </Space>
          ) : undefined}
        >
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            items={[
              {
                key: 'dashboard',
                label: <span><DashboardOutlined /> 概览看板</span>,
                children: <FleetDashboardPage />,
              },
              {
                key: 'enterprises',
                label: <span><TeamOutlined /> 车队企业</span>,
                children: (
                  <>
                    {enterpriseError && (
                      <Alert type="error" showIcon style={{ marginBottom: 12 }}
                        message="车队企业加载失败" description={enterpriseError}
                        action={<Button size="small" icon={<ReloadOutlined />} onClick={loadEnterprises}>重试</Button>}
                      />
                    )}
                    <Table columns={enterpriseColumns} dataSource={filteredEnterprises} rowKey="id" loading={enterpriseLoading} scroll={{ x: 960 }}
                      pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }}
                    />
                  </>
                ),
              },
              {
                key: 'vehicles',
                label: <span><CarOutlined /> 车辆管理</span>,
                children: <FleetVehiclesPage />,
              },
              {
                key: 'funds',
                label: <span><DollarOutlined /> 资金账户</span>,
                children: (
                  <>
                    {fundError && (
                      <Alert type="error" showIcon style={{ marginBottom: 12 }}
                        message="资金账户加载失败" description={fundError}
                        action={<Button size="small" icon={<ReloadOutlined />} onClick={loadFunds}>重试</Button>}
                      />
                    )}
                    <Table columns={fundColumns} dataSource={filteredFunds} rowKey="id" loading={fundLoading} scroll={{ x: 1040 }}
                      pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }}
                    />
                  </>
                ),
              },
              {
                key: 'recharge',
                label: <span><DollarOutlined /> 充值</span>,
                children: <FleetRechargePage />,
              },
              {
                key: 'drivers',
                label: <span><IdcardOutlined /> 司机管理</span>,
                children: <FleetDriversPage />,
              },
              {
                key: 'carbon',
                label: <span><ExperimentOutlined /> 碳排放</span>,
                children: <FleetCarbonPage />,
              },
              {
                key: 'charging-schedule',
                label: <span><ScheduleOutlined /> 智能充电调度</span>,
                children: <FleetChargingSchedulePage />,
              },
              {
                key: 'settlement',
                label: <span><FileTextOutlined /> 费用结算</span>,
                children: <FleetSettlementPage />,
              },
              {
                key: 'settings',
                label: <span><SettingOutlined /> 设置</span>,
                children: <FleetSettingsPage />,
              },
              {
                key: 'policies',
                label: <span><SlidersOutlined /> 充电策略</span>,
                children: <FleetChargingPoliciesPage />,
              },
              {
                key: 'attendance',
                label: <span><CalendarOutlined /> 司机考勤</span>,
                children: <FleetAttendancePage />,
              },
              {
                key: 'carbon-cert',
                label: <span><FileProtectOutlined /> 碳核证</span>,
                children: <FleetCarbonCertificatesPage />,
              },
              {
                key: 'maintenance',
                label: <span><ToolOutlined /> 维保保险</span>,
                children: <FleetVehicleMaintenancePage />,
              },
              {
                key: 'insurance',
                label: <span><SafetyOutlined /> 车辆保险</span>,
                children: <FleetVehicleInsurancePage />,
              },
              {
                key: 'charging-stats',
                label: <span><FundOutlined /> 充电统计</span>,
                children: <FleetChargingStatsPage />,
              },
            ]}
          />
        </Card>

        {/* 车队企业 Modal */}
        <Modal
          title={editingItem ? '编辑车队企业' : '新增车队企业'}
          open={enterpriseModalOpen}
          onOk={handleEnterpriseSubmit}
          onCancel={() => { setEnterpriseModalOpen(false); enterpriseForm.resetFields(); setEditingItem(null); }}
          width={modalWidth}
          destroyOnHidden
        >
          <Form form={enterpriseForm} layout="vertical">
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="name" label="企业名称" rules={[{ required: true, message: '请输入企业名称' }]}>
                  <Input placeholder="请输入企业名称" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="code" label="企业编码" rules={[{ required: true, message: '请输入企业编码' }]}>
                  <Input placeholder="如 TL-FLEET-001" disabled={!!editingItem} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="contact" label="联系人">
                  <Input placeholder="请输入联系人" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="phone" label="联系电话">
                  <Input placeholder="请输入联系电话" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="address" label="地址">
              <Input placeholder="请输入地址" />
            </Form.Item>
            <Form.Item name="status" label="状态" initialValue="active">
              <Select>
                <Select.Option value="active">启用</Select.Option>
                <Select.Option value="inactive">停用</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input.TextArea rows={2} placeholder="请输入描述" />
            </Form.Item>
          </Form>
        </Modal>

        {/* 资金账户 Modal */}
        <Modal
          title={editingItem ? '编辑资金账户' : '新增资金账户'}
          open={fundModalOpen}
          onOk={handleFundSubmit}
          onCancel={() => { setFundModalOpen(false); fundForm.resetFields(); setEditingItem(null); }}
          width={modalWidth}
          destroyOnHidden
        >
          <Form form={fundForm} layout="vertical">
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="account_name" label="账户名称" rules={[{ required: true, message: '请输入账户名称' }]}>
                  <Input placeholder="请输入账户名称" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="account_type" label="账户类型" rules={[{ required: true, message: '请选择账户类型' }]}>
                  <Select placeholder="选择账户类型">
                    {FUND_TYPES.map(t => <Select.Option key={t} value={t}>{t}</Select.Option>)}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="enterprise_id" label="所属企业" rules={[{ required: true, message: '请选择企业' }]}>
                  <Select placeholder="选择所属企业" showSearch optionFilterProp="label">
                    {enterprises.map(e => <Select.Option key={e.id} value={e.id} label={e.name}>{e.name}</Select.Option>)}
                  </Select>
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="balance" label="余额" initialValue={0}>
                  <InputNumber style={{ width: '100%' }} placeholder="请输入余额" min={0} step={0.01} precision={2}
                    formatter={value => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="bank_name" label="开户银行">
                  <Input placeholder="请输入开户银行" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="bank_account" label="银行账号">
                  <Input placeholder="请输入银行账号" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="currency" label="币种" initialValue="¥">
                  <Select>
                    <Select.Option value="¥">人民币 (¥)</Select.Option>
                    <Select.Option value="$">美元 ($)</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="status" label="状态" initialValue="active">
                  <Select>
                    <Select.Option value="active">正常</Select.Option>
                    <Select.Option value="frozen">冻结</Select.Option>
                    <Select.Option value="inactive">停用</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="description" label="描述">
              <Input.TextArea rows={2} placeholder="请输入描述" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetPage;
