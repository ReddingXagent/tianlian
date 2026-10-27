/**
 * 天链 V3 - 用户类型管理页面
 * P0 运营核心补齐：5种用户类型统一管理、筛选、统计
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Input, Select, message, Popconfirm,
  Modal, Form, Tabs, Badge,
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
  TeamOutlined, CarOutlined, BarChartOutlined, LaptopOutlined, MobileOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import PageWrapper from '../../components/PageWrapper';

/* ── 类型定义 ── */
interface User {
  id: number;
  username: string;
  real_name?: string;
  phone?: string;
  email?: string;
  role: string;
  status: string;
  last_login?: string;
  created_at?: string;
}

const USER_TYPE_CONFIG: Record<string, { label: string; icon: any; color: string; description: string }> = {
  app: { label: 'APP用户', icon: MobileOutlined, color: '#1890ff', description: '通过手机App注册的普通用户' },
  card: { label: '卡用户', icon: TeamOutlined, color: '#722ed1', description: '使用实体充电卡的用户' },
  vin: { label: 'VIN用户', icon: CarOutlined, color: '#13c2c2', description: '通过车辆VIN码识别的用户' },
  interconnect: { label: '互联互通用户', icon: LaptopOutlined, color: '#52c41a', description: '跨平台互联互通协议用户' },
  enterprise: { label: '企业用户', icon: BarChartOutlined, color: '#faad14', description: '企业账户下的员工/车辆用户' },
};

/* ── 组件 ── */
const UserTypeManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('all');
  const [users, setUsers] = useState<User[]>([]);
  const [stats, setStats] = useState<any>({});
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const [form] = Form.useForm();

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const extraParams: Record<string, unknown> = {};
      if (activeTab === 'active') {
        // 活跃用户Tab：按status=active筛选，不传user_type；忽略statusFilter避免冲突
        extraParams.status = 'active';
      } else {
        if (activeTab !== 'all') extraParams.user_type = activeTab;
        if (statusFilter) extraParams.status = statusFilter;
      }
      if (searchText) extraParams.search = searchText;
      const users = await fetchAllPages<User>((params) => api.get('/operate/users', { params }), extraParams);
      setUsers(users);
    } catch (e) {
      message.error('加载用户列表失败');
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter, searchText]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/operate/users/stats');
      setStats(res.data || {});
    } catch { }
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchStats();
  }, [fetchUsers, fetchStats]);

  const openEdit = (record: User) => {
    setEditingUser(record);
    form.setFieldsValue({
      username: record.username,
      real_name: record.real_name || '',
      phone: record.phone || '',
      email: record.email || '',
      status: record.status,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      await api.put(`/operate/users/${editingUser?.id}`, values);
      message.success('更新成功');
      setModalOpen(false);
      fetchUsers();
    } catch (e) {
      message.error('更新失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      // Note: No delete API for users currently
      message.warning('删除用户功能暂未开放，可通过状态设为inactive');
    } catch { message.error('操作失败'); }
  };

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 130 },
    { title: '真实姓名', dataIndex: 'real_name', key: 'real_name', width: 100 },
    { title: '手机号', dataIndex: 'phone', key: 'phone', width: 120 },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 150 },
    { title: '用户类型', dataIndex: 'role', key: 'role', width: 120,
      render: (v: string) => {
        const c = USER_TYPE_CONFIG[v];
        return c ? (
          <Tag color={c.color}>
            <c.icon style={{marginRight: 4}} />{c.label}
          </Tag>
        ) : <Tag color="default">{v}</Tag>;
      } },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => {
        const colors: Record<string, string> = { active: 'green', inactive: 'red', suspended: 'orange' };
        return <Tag color={colors[v] || 'default'}>{v === 'active' ? '正常' : v === 'inactive' ? '停用' : '冻结'}</Tag>;
      } },
    { title: '最后登录', dataIndex: 'last_login', key: 'last_login', width: 150,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '未登录' },
    { title: '注册时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: unknown, record: User) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
        </Space>
      ),
    },
  ];

  // 用户类型Tab配置
  const typeTabs = [
    { key: 'all', label: '全部用户', count: stats.total || 0 },
    { key: 'active', label: '活跃用户', count: stats.active_count || 0 },
    { key: 'app', label: 'APP用户', count: stats.by_user_type?.app || 0 },
    { key: 'card', label: '卡用户', count: stats.by_user_type?.card || 0 },
    { key: 'vin', label: 'VIN用户', count: stats.by_user_type?.vin || 0 },
    { key: 'interconnect', label: '互联互通', count: stats.by_user_type?.interconnect || 0 },
    { key: 'enterprise', label: '企业用户', count: stats.by_user_type?.enterprise || 0 },
  ];

  return (
    <PageWrapper
      loading={loading}
      skeletonType="table"
      skeletonCount={5}
      hasData={users.length > 0}
      empty={{ type: 'default', title: '暂无用户', description: '该类型下暂无用户', actionText: '刷新', onAction: fetchUsers }}
      onRetry={fetchUsers}
      transition="slide-up"
    >
      <div className="page-container">
        {/* 用户列表 */}
        <Card extra={
          <Space>
            {activeTab !== 'active' && (
              <Select
                placeholder="按状态筛选"
                value={statusFilter}
                onChange={setStatusFilter}
                style={{ width: 120 }}
                allowClear
                options={[
                  { value: 'active', label: '正常' },
                  { value: 'inactive', label: '停用' },
                  { value: 'suspended', label: '冻结' },
                ]}
              />
            )}
            <Input placeholder="搜索用户名/手机/姓名" prefix={<SearchOutlined />} value={searchText} onChange={e => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
            <Button icon={<ReloadOutlined />} onClick={fetchUsers}>刷新</Button>
          </Space>
        }>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={typeTabs.map(t => ({
              key: t.key,
              label: (
                <span>
                  {USER_TYPE_CONFIG[t.key] && (() => {
                    const Icon = USER_TYPE_CONFIG[t.key].icon;
                    return <Icon style={{marginRight: 4, color: USER_TYPE_CONFIG[t.key].color}} />;
                  })()}
                  {t.label} ({t.count})
                </span>
              ),
              children: (
                <AutoHeightTable
                  scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
                  columns={columns}
                  dataSource={users}
                  rowKey="id"
                  loading={loading}
                  pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }}
                />
              ),
            }))}
          />
        </Card>

        {/* 编辑弹窗 */}
        <Modal
          title="编辑用户信息"
          open={modalOpen}
          onCancel={() => setModalOpen(false)}
          onOk={() => form.validateFields().then(handleSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={520}
          destroyOnHidden
        >
          <Form form={form} layout="vertical" colon={false}>
            <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
              <Input disabled />
            </Form.Item>
            <Form.Item name="real_name" label="真实姓名">
              <Input />
            </Form.Item>
            <Form.Item name="phone" label="手机号">
              <Input />
            </Form.Item>
            <Form.Item name="email" label="邮箱">
              <Input />
            </Form.Item>
            <Form.Item name="status" label="状态" rules={[{ required: true }]}>
              <Select placeholder="选择状态" options={[
                { value: 'active', label: '正常' },
                { value: 'inactive', label: '停用' },
                { value: 'suspended', label: '冻结' },
              ]} />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default UserTypeManagement;