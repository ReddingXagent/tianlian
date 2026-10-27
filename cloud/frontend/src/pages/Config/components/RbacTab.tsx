/**
 * 天链 V3 - 系统配置：权限配置 Tab
 */
import React from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  Tooltip, Row, Col, Statistic, Tabs, Tree, Popconfirm,
} from 'antd';
import AutoHeightTable from '../../../components/AutoHeightTable';
import {
  SafetyCertificateOutlined, PlusOutlined, ReloadOutlined,
  EditOutlined, DeleteOutlined, WarningOutlined,
} from '@ant-design/icons';
import { useRbac } from '../hooks/useRbac';
import { RESOURCE_LABEL, ROLE_COLOR_MAP } from '../constants';
import type { RoleItem } from '../types';

const { Option } = Select;

const RbacTab: React.FC = () => {
  const {
    roles, allPermissions, rbacLoading,
    roleModalVisible, setRoleModalVisible, editingRole,
    roleForm, permissionGroups, permissionTreeData,
    fetchRoles, openCreateRole, openEditRole, handleRoleSubmit, handleDeleteRole,
  } = useRbac();

  const roleColumns = [
    { title: '角色名', dataIndex: 'display_name', key: 'display_name', width: 120 },
    {
      title: '标识', dataIndex: 'name', key: 'name', width: 100,
      render: (name: string) => <Tag color={ROLE_COLOR_MAP[name]}>{name}</Tag>,
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

  return (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="角色" value={roles.length} prefix={<SafetyCertificateOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="权限项" value={allPermissions.length} prefix={<WarningOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card
        title={<Space><SafetyCertificateOutlined />角色管理</Space>}
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateRole}>新建角色</Button>
            <Button icon={<ReloadOutlined />} onClick={fetchRoles}>刷新</Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <AutoHeightTable
          scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
          columns={roleColumns}
          dataSource={roles}
          rowKey="id"
          loading={rbacLoading}
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

      <Card title={<Space><SafetyCertificateOutlined />权限矩阵</Space>}>
        <Tabs
          size="small"
          items={[
            {
              key: 'tree',
              label: '权限树形图',
              children: (
                <Tree
                  showLine={{ showLeafIcon: false }}
                  defaultExpandAll
                  treeData={permissionTreeData}
                  style={{ padding: '8px 0' }}
                />
              ),
            },
            {
              key: 'cards',
              label: '按模块分组',
              children: (
                <>
                  {Object.entries(permissionGroups).map(([resource, perms]) => (
                    <Card
                      key={resource}
                      type="inner"
                      title={RESOURCE_LABEL[resource] || resource}
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
                </>
              ),
            },
          ]}
        />
      </Card>

      {/* 角色弹窗 */}
      <Modal
        title={editingRole ? '编辑角色' : '新建角色'}
        open={roleModalVisible}
        onOk={handleRoleSubmit}
        onCancel={() => setRoleModalVisible(false)}
        okText="保存" cancelText="取消" width={640}
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
                  {RESOURCE_LABEL[p.resource] || p.resource} - {p.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default RbacTab;
