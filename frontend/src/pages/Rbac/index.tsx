/**
 * 权限管理页面 V2 — 支持角色管理 + 用户角色分配 + 自定义角色
 */
import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  message, Tabs, Popconfirm, Tooltip, Row, Col, Statistic,
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  TeamOutlined, SafetyCertificateOutlined, UserOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { rbacAPI } from '../../api';

const { Option } = Select;

interface PermissionItem {
  name: string;
  resource: string;
  action: string;
  label: string;
}

interface RoleItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
  user_count: number;
}

interface ExtraRole {
  id: number;
  name: string;
  display_name: string;
}

interface RbacUser {
  id: number;
  username: string;
  real_name: string;
  role: string;
  role_label: string;
  extra_roles: ExtraRole[];
  status: string;
  permissions: string[];
}

const RbacPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('roles');
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [allPermissions, setAllPermissions] = useState<PermissionItem[]>([]);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [userPage, setUserPage] = useState(1);
  const [userPageSize, setUserPageSize] = useState(10);
  const [loading, setLoading] = useState(false);

  // Role modal
  const [roleModalVisible, setRoleModalVisible] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [roleForm] = Form.useForm();

  // User role modal
  const [userModalVisible, setUserModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<RbacUser | null>(null);
  const [userForm] = Form.useForm();

  useEffect(() => {
    fetchRoles();
    fetchPermissions();
    fetchUsers();
  }, []);

  const fetchRoles = async () => {
    setLoading(true);
    try {
      const res: any = await rbacAPI.roles();
      setRoles(res.items || []);
    } catch { message.error('获取角色列表失败'); }
    finally { setLoading(false); }
  };

  const fetchPermissions = async () => {
    try {
      const res: any = await rbacAPI.permissions();
      setAllPermissions(res.items || []);
    } catch { /* ignore */ }
  };

  const fetchUsers = async (page = userPage, pageSize = userPageSize) => {
    try {
      const res: any = await rbacAPI.rbacUsers({ page, page_size: pageSize });
      setUsers(res.items || []);
      setUserTotal(res.total || 0);
    } catch { message.error('获取用户列表失败'); }
  };

  const handleUserTableChange = (page: number, pageSize: number) => {
    const next = pageSize !== userPageSize ? 1 : page;
    setUserPage(next);
    setUserPageSize(pageSize);
    fetchUsers(next, pageSize);
  };

  // Convert permission names to groups
  const permissionGroups = useMemo(() => {
    const groups: Record<string, PermissionItem[]> = {};
    allPermissions.forEach(p => {
      const group = p.resource || 'other';
      if (!groups[group]) groups[group] = [];
      groups[group].push(p);
    });
    return groups;
  }, [allPermissions]);

  const resourceLabel: Record<string, string> = {
    device: '设备管理',
    workorder: '工单管理',
    alarm: '告警管理',
    station: '站点管理',
    user: '用户管理',
    report: '报表',
    audit: '审计日志',
    system: '系统管理',
  };

  // ── Role CRUD ──

  const openCreateRole = () => {
    setEditingRole(null);
    roleForm.resetFields();
    setRoleModalVisible(true);
  };

  const openEditRole = (role: RoleItem) => {
    setEditingRole(role);
    roleForm.setFieldsValue({
      name: role.name,
      display_name: role.display_name,
      description: role.description,
      permissions: role.permissions,
    });
    setRoleModalVisible(true);
  };

  const handleRoleSubmit = async () => {
    try {
      const values = await roleForm.validateFields();
      if (editingRole) {
        await rbacAPI.updateRole(editingRole.id, {
          display_name: values.display_name,
          description: values.description,
          permissions: values.permissions || [],
        });
        message.success('角色更新成功');
      } else {
        await rbacAPI.createRole({
          name: values.name,
          display_name: values.display_name,
          description: values.description,
          permissions: values.permissions || [],
        });
        message.success('角色创建成功');
      }
      setRoleModalVisible(false);
      fetchRoles();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const handleDeleteRole = async (role: RoleItem) => {
    try {
      await rbacAPI.deleteRole(role.id);
      message.success(`角色 ${role.display_name} 已删除`);
      fetchRoles();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败');
    }
  };

  // ── User role assignment ──

  const openUserRoleModal = (user: RbacUser) => {
    setEditingUser(user);
    userForm.setFieldsValue({
      role: user.role,
    });
    setUserModalVisible(true);
  };

  const handleUserRoleSubmit = async () => {
    try {
      const values = await userForm.validateFields();
      if (!editingUser) return;
      await rbacAPI.updateUserRole(editingUser.id, {
        role: values.role,
        extra_role_ids: values.extra_role_ids || [],
      });
      message.success('用户角色更新成功');
      setUserModalVisible(false);
      fetchUsers();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  // ── Color maps ──

  const roleColorMap: Record<string, string> = {
    admin: 'red',
    operator: 'blue',
    viewer: 'default',
    auditor: 'orange',
  };

  const roleTextMap: Record<string, string> = {
    admin: '管理员',
    operator: '运维操作员',
    viewer: '只读用户',
    auditor: '审计员',
    engineer: '工程师',
  };

  // ── Role columns ──

  const roleColumns = [
    { title: '角色名', dataIndex: 'display_name', key: 'display_name', width: 120 },
    {
      title: '标识', dataIndex: 'name', key: 'name', width: 100,
      render: (name: string) => <Tag color={roleColorMap[name]}>{name}</Tag>,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '用户数', dataIndex: 'user_count', key: 'user_count', width: 80,
      render: (c: number) => <Tag color={c > 0 ? 'blue' : 'default'}>{c}</Tag>,
    },
    {
      title: '类型', dataIndex: 'is_system', key: 'is_system', width: 70,
      render: (s: boolean) => s ? <Tag color="green">内置</Tag> : <Tag color="orange">自定义</Tag>,
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: any, record: RoleItem) => (
        <Space>
          <Tooltip title="编辑权限">
            <Button type="link" icon={<EditOutlined />} onClick={() => openEditRole(record)} />
          </Tooltip>
          {!record.is_system && (
            <Popconfirm title={`确定删除角色 "${record.display_name}"？`}
              onConfirm={() => handleDeleteRole(record)} okText="删除" cancelText="取消">
              <Button type="link" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // ── User columns ──

  const userColumns = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 100 },
    { title: '姓名', dataIndex: 'real_name', key: 'real_name', width: 100 },
    {
      title: '主角色', dataIndex: 'role', key: 'role', width: 100,
      render: (role: string) => (
        <Tag color={roleColorMap[role]}>{roleTextMap[role] || role}</Tag>
      ),
    },
    {
      title: '附加角色', dataIndex: 'extra_roles', key: 'extra_roles', width: 150,
      render: (roles: ExtraRole[]) => !roles?.length
        ? <span style={{ color: '#999' }}>无</span>
        : roles.map(r => <Tag key={r.id}>{r.display_name || r.name}</Tag>),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 70,
      render: (s: string) => (
        <Tag color={s === 'active' ? 'green' : 'red'}>{s === 'active' ? '正常' : '停用'}</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: any, record: RbacUser) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openUserRoleModal(record)}>
          分配角色
        </Button>
      ),
    },
  ];

  // ── Permission table ──

  const permissionColumns = [
    {
      title: '模块', dataIndex: 'resource', key: 'resource', width: 100,
      render: (r: string) => resourceLabel[r] || r,
    },
    { title: '权限名', dataIndex: 'name', key: 'name', width: 180,
      render: (n: string) => <code>{n}</code> },
    { title: '说明', dataIndex: 'label', key: 'label' },
    { title: '操作', dataIndex: 'action', key: 'action', width: 80 },
  ];

  return (
    <div className="page-container">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="角色" value={roles.length} prefix={<SafetyCertificateOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="用户" value={userTotal} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="权限项" value={allPermissions.length} prefix={<WarningOutlined />} />
          </Card>
        </Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <Tabs.TabPane tab="角色管理" key="roles">
          <Card
            title={<Space><SafetyCertificateOutlined />角色管理</Space>}
            extra={
              <Space>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateRole}>
                  新建角色
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchRoles}>刷新</Button>
              </Space>
            }
          >
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              columns={roleColumns}
              dataSource={roles}
              rowKey="id"
              loading={loading}
              pagination={false}
              expandable={{
                expandedRowRender: (record: RoleItem) => (
                  <div style={{ margin: 0, padding: '8px 0' }}>
                    <Space wrap>
                      <Tag color="blue" style={{ fontWeight: 'bold' }}>权限列表:</Tag>
                      {record.permissions.map(p => {
                        const permInfo = allPermissions.find(ap => ap.name === p);
                        return <Tag key={p}>{permInfo?.label || p}</Tag>;
                      })}
                      {!record.permissions.length && <span style={{ color: '#999' }}>无权限</span>}
                    </Space>
                  </div>
                ),
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="用户角色分配" key="users">
          <Card
            title={<Space><TeamOutlined />用户角色分配</Space>}
            extra={<Button icon={<ReloadOutlined />} onClick={() => fetchUsers()}>刷新</Button>}
          >
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              columns={userColumns}
              dataSource={users}
              rowKey="id"
              pagination={{
                current: userPage,
                total: userTotal,
                pageSize: userPageSize,
                pageSizeOptions: [10, 20, 50],
                showSizeChanger: true,
                showTotal: (t: number) => `共 ${t} 人`,
                onChange: handleUserTableChange,
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="权限矩阵" key="permissions">
          <Card title={<Space><SafetyCertificateOutlined />权限矩阵</Space>}>
            {Object.entries(permissionGroups).map(([resource, perms]) => (
              <Card
                key={resource}
                type="inner"
                title={resourceLabel[resource] || resource}
                size="small"
                style={{ marginBottom: 12 }}
              >
                <Space wrap>
                  {perms.map(p => (
                    <Tag key={p.name} color="blue" style={{ cursor: 'default' }}>
                      {p.label} <code style={{ fontSize: 11 }}>({p.name})</code>
                    </Tag>
                  ))}
                </Space>
              </Card>
            ))}
          </Card>
        </Tabs.TabPane>
      </Tabs>

      {/* Role modal */}
      <Modal
        title={editingRole ? '编辑角色' : '新建角色'}
        open={roleModalVisible}
        onOk={handleRoleSubmit}
        onCancel={() => setRoleModalVisible(false)}
        okText="保存"
        cancelText="取消"
        width={640}
      >
        <Form form={roleForm} layout="vertical">
          {!editingRole && (
            <Form.Item name="name" label="角色标识" rules={[{ required: true, message: '请输入角色标识' }]}>
              <Input placeholder="例如: custom_role" />
            </Form.Item>
          )}
          <Form.Item name="display_name" label="角色名称" rules={[{ required: true, message: '请输入角色名称' }]}>
            <Input placeholder="例如: 自定义角色" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="角色描述" />
          </Form.Item>
          <Form.Item name="permissions" label="权限">
            <Select mode="multiple" placeholder="选择权限" style={{ width: '100%' }}>
              {allPermissions.map(p => (
                <Option key={p.name} value={p.name}>
                  {resourceLabel[p.resource] || p.resource} - {p.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* User role modal */}
      <Modal
        title={`分配角色 - ${editingUser?.real_name || editingUser?.username}`}
        open={userModalVisible}
        onOk={handleUserRoleSubmit}
        onCancel={() => setUserModalVisible(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={userForm} layout="vertical">
          <Form.Item name="role" label="主角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select placeholder="选择主角色">
              {roles.filter(r => r.is_system).map(r => (
                <Option key={r.name} value={r.name}>{r.display_name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="extra_role_ids" label="附加角色">
            <Select mode="multiple" placeholder="选择附加角色（可选）" style={{ width: '100%' }}>
              {roles.map(r => (
                <Option key={r.id} value={r.id}>{r.display_name}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RbacPage;