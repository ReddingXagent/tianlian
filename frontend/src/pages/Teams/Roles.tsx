/**
 * 天链 V3 — 团队角色管理页面
 * 左侧: 角色列表 + CRUD | 右侧: 权限树形图
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Tree,
  message, Popconfirm, Tooltip, Row, Col, Descriptions,
  Spin, Empty, Typography,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  SafetyCertificateOutlined, ApartmentOutlined, TeamOutlined,
  KeyOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import api from '../../api';

const { Text, Title } = Typography;
const { TextArea } = Input;

/* ── types ── */
interface RoleItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
  permission_labels?: Record<string, string>;
  user_count: number;
  created_at?: string;
}

interface TreeNode extends DataNode {
  name?: string;
  resource?: string;
  action?: string;
  is_leaf?: boolean;
}

/* ── API helpers ── */
const rolesAPI = api;

async function fetchRoles(): Promise<RoleItem[]> {
  const res = await rolesAPI.get('/roles');
  return res.data?.items ?? [];
}

async function fetchPermissionTree(): Promise<TreeNode[]> {
  const res = await rolesAPI.get('/roles/tree');
  return res.data?.tree ?? [];
}

async function createRole(data: { name: string; display_name: string; description: string; permissions: string[] }) {
  return rolesAPI.post('/roles', data);
}

async function updateRole(id: number, data: { display_name?: string; description?: string; permissions?: string[] }) {
  return rolesAPI.put(`/roles/${id}`, data);
}

async function deleteRole(id: number) {
  return rolesAPI.delete(`/roles/${id}`);
}

/* ── helper ── */
function getRoleColor(name: string): string {
  const map: Record<string, string> = {
    super_admin: 'purple', admin: 'red', operator: 'blue',
    viewer: 'green', auditor: 'orange',
  };
  return map[name] ?? 'cyan';
}

function getRoleLabel(name: string): string {
  const map: Record<string, string> = {
    super_admin: '超级管理员', admin: '管理员', operator: '运维操作员',
    viewer: '只读用户', auditor: '审计员',
  };
  return map[name] ?? name;
}

/* ══════════════════════════ Component ══════════════════════════ */
const TeamsRolesPage: React.FC = () => {
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [permTree, setPermTree] = useState<TreeNode[]>([]);
  const [permTreeLoading, setPermTreeLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<RoleItem | null>(null);

  /* ── Modal states ── */
  const [modalVisible, setModalVisible] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [modalLoading, setModalLoading] = useState(false);
  const [form] = Form.useForm();
  const [checkedPermissions, setCheckedPermissions] = useState<string[]>([]);

  /* ── Load data ── */
  const loadRoles = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchRoles();
      setRoles(items);
      if (items.length > 0 && !selectedRole) {
        setSelectedRole(items[0]);
      }
    } catch (e: any) {
      message.error('加载角色列表失败: ' + (e?.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  }, [selectedRole]);

  const loadPermTree = useCallback(async () => {
    setPermTreeLoading(true);
    try {
      const tree = await fetchPermissionTree();
      setPermTree(tree);
    } catch (e: any) {
      message.error('加载权限树失败');
    } finally {
      setPermTreeLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRoles();
    loadPermTree();
  }, []);

  /* ── Handlers ── */
  const openCreateModal = () => {
    setModalMode('create');
    setCheckedPermissions([]);
    form.resetFields();
    setModalVisible(true);
  };

  const openEditModal = (role: RoleItem) => {
    setModalMode('edit');
    const currentPerms = role.permissions || [];
    setCheckedPermissions([...currentPerms]);
    form.setFieldsValue({
      name: role.name,
      display_name: role.display_name,
      description: role.description,
    });
    setModalVisible(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);

      if (modalMode === 'create') {
        await createRole({ ...values, permissions: checkedPermissions });
        message.success('角色创建成功');
      } else if (selectedRole) {
        await updateRole(selectedRole.id, { ...values, permissions: checkedPermissions });
        message.success('角色更新成功');
      }

      setModalVisible(false);
      loadRoles();
    } catch (e: any) {
      if (e?.errorFields) return; // form validation
      message.error('操作失败: ' + (e?.response?.data?.message || e?.message || '未知错误'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = async (role: RoleItem) => {
    try {
      await deleteRole(role.id);
      message.success(`角色 ${role.display_name} 已删除`);
      if (selectedRole?.id === role.id) setSelectedRole(null);
      loadRoles();
    } catch (e: any) {
      message.error('删除失败: ' + (e?.response?.data?.message || e?.message));
    }
  };

  const onPermTreeCheck = (checked: any) => {
    setCheckedPermissions(checked as string[]);
  };

  /* ── Table columns ── */
  const columns = [
    {
      title: '角色',
      key: 'role',
      width: 200,
      render: (_: any, r: RoleItem) => (
        <Space>
          <SafetyCertificateOutlined style={{ color: getRoleColor(r.name) }} />
          <span style={{ fontWeight: 500 }}>{r.display_name}</span>
          <Tag color={getRoleColor(r.name)}>{getRoleLabel(r.name)}</Tag>
          {r.is_system && <Tag>系统内置</Tag>}
        </Space>
      ),
    },
    {
      title: '权限数',
      dataIndex: 'permissions',
      width: 80,
      render: (p: string[]) => <Tag color="blue">{p?.length ?? 0}</Tag>,
    },
    {
      title: '用户数',
      dataIndex: 'user_count',
      width: 80,
      render: (n: number) => <><TeamOutlined style={{ marginRight: 4 }} />{n}</>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, r: RoleItem) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="link" size="small" icon={<EditOutlined />}
              onClick={() => {
                setSelectedRole(r);
                openEditModal(r);
              }}
            />
          </Tooltip>
          {!r.is_system && (
            <Popconfirm
              title={`确定删除角色「${r.display_name}」?`}
              onConfirm={() => handleDelete(r)}
              okText="确认删除"
              cancelText="取消"
            >
              <Tooltip title="删除">
                <Button type="link" size="small" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '0 0 24px' }}>
      {/* ── Header ── */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <KeyOutlined style={{ marginRight: 8 }} />
            角色权限管理
          </Title>
          <Text type="secondary" style={{ marginLeft: 32 }}>
            配置团队角色和对应的权限
          </Text>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadRoles(); loadPermTree(); }}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              新建角色
            </Button>
          </Space>
        </Col>
      </Row>

      {/* ── Main content: Left list + Right detail ── */}
      <Row gutter={16}>
        {/* 左侧: 角色列表 */}
        <Col xs={24} lg={10}>
          <Card
            title={<><ApartmentOutlined /> 角色列表</>}
            size="small"
            style={{ height: '100%', minHeight: 400 }}
          >
            <Spin spinning={loading}>
              <Table
                dataSource={roles}
                columns={columns}
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ y: 420 }}
                onRow={(record) => ({
                  onClick: () => setSelectedRole(record),
                  style: {
                    cursor: 'pointer',
                    background: selectedRole?.id === record.id ? '#e6f7ff' : undefined,
                  },
                })}
                locale={{ emptyText: <Empty description="暂无角色" /> }}
              />
            </Spin>
          </Card>
        </Col>

        {/* 右侧: 权限树形图 + 角色详情 */}
        <Col xs={24} lg={14}>
          {selectedRole ? (
            <>
              <Card
                title={<><CheckCircleOutlined /> 角色详情</>}
                size="small"
                style={{ marginBottom: 16 }}
              >
                <Descriptions size="small" column={2}>
                  <Descriptions.Item label="角色名">{selectedRole.name}</Descriptions.Item>
                  <Descriptions.Item label="显示名">
                    <Tag color={getRoleColor(selectedRole.name)}>
                      {selectedRole.display_name}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="类型">
                    {selectedRole.is_system ? <Tag>系统内置</Tag> : <Tag color="cyan">自定义</Tag>}
                  </Descriptions.Item>
                  <Descriptions.Item label="权限数">
                    <Tag color="blue">{selectedRole.permissions?.length ?? 0}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="用户数">
                    <TeamOutlined style={{ marginRight: 4 }} />
                    {selectedRole.user_count ?? 0}
                  </Descriptions.Item>
                  <Descriptions.Item label="说明" span={2}>
                    {selectedRole.description || '-'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>

              <Card
                title={<><ApartmentOutlined /> 权限树形图</>}
                size="small"
                extra={
                  <Button
                    size="small"
                    type="primary"
                    icon={<EditOutlined />}
                    onClick={() => openEditModal(selectedRole)}
                  >
                    编辑权限
                  </Button>
                }
              >
                <Spin spinning={permTreeLoading}>
                  {permTree.length > 0 ? (
                    <div
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Tree
                        checkable
                        checkedKeys={selectedRole.permissions || []}
                        disabled
                        treeData={permTree}
                        defaultExpandAll
                        style={{ maxHeight: 420, overflow: 'auto' }}
                      />
                    </div>
                  ) : (
                    <Empty description="暂无权限数据" />
                  )}
                </Spin>
              </Card>
            </>
          ) : (
            <Card size="small">
              <Empty description="请选择一个角色查看详情" />
            </Card>
          )}
        </Col>
      </Row>

      {/* ── Modal: 创建/编辑角色 ── */}
      <Modal
        title={modalMode === 'create' ? '新建角色' : '编辑角色'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {modalMode === 'create' && (
            <Form.Item
              name="name"
              label="角色标识"
              rules={[
                { required: true, message: '请输入角色标识' },
                { pattern: /^[a-z_][a-z0-9_]*$/, message: '仅支持小写英文、数字和下划线' },
              ]}
            >
              <Input placeholder="例如: team_leader" />
            </Form.Item>
          )}
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="例如: 团队负责人" />
          </Form.Item>
          <Form.Item name="description" label="角色说明">
            <TextArea rows={2} placeholder="描述该角色的职责范围..." />
          </Form.Item>
          <Form.Item label="选择权限">
            <Spin spinning={permTreeLoading}>
              {permTree.length > 0 ? (
                <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, padding: 12, maxHeight: 350, overflow: 'auto' }}>
                  <Tree
                    checkable
                    checkedKeys={checkedPermissions}
                    onCheck={onPermTreeCheck}
                    treeData={permTree}
                    defaultExpandAll
                  />
                </div>
              ) : (
                <Empty description="加载权限树中..." />
              )}
            </Spin>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TeamsRolesPage;
