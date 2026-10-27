/**
 * 天链 V3 - 用户管理页面（筑基1增强版）
 */
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Table, Card, Button, Space, Tag, Modal, Form, Input, Select, message, Popconfirm, Descriptions, Row, Col, Statistic } from 'antd';
import { PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined, LockOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons';
import { userAPI } from '../../api';

const UsersPage: React.FC = () => {
  const { t } = useTranslation();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const loadUsers = async () => {
    setLoading(true);
    try {
      const res: any = await userAPI.list();
      setUsers(res.data?.items || res.data || []);
    } catch (err) {
      message.error(t('pages.users.load_failed'));
    }
    setLoading(false);
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const roleColorMap: Record<string, string> = {
    admin: 'red',
    manager: 'blue',
    operator: 'green',
    viewer: 'default',
  };

  const roleTextMap: Record<string, string> = {
    admin: t('pages.users.role_admin'),
    manager: t('pages.users.role_manager'),
    operator: t('pages.users.role_operator'),
    viewer: t('pages.users.role_viewer'),
  };

  const statusColorMap: Record<string, string> = {
    active: 'green',
    inactive: 'default',
    locked: 'red',
  };

  const statusTextMap: Record<string, string> = {
    active: t('pages.users.status_active'),
    inactive: t('pages.users.status_inactive'),
    locked: t('pages.users.status_locked'),
  };

  // 筛选数据
  const filteredUsers = users.filter((u: any) => {
    const matchSearch = !searchText || 
      u.username?.toLowerCase().includes(searchText.toLowerCase()) ||
      u.real_name?.includes(searchText);
    const matchRole = roleFilter === 'all' || u.role === roleFilter;
    const matchStatus = statusFilter === 'all' || u.status === statusFilter;
    return matchSearch && matchRole && matchStatus;
  });

  const stats = {
    total: users.length,
    active: users.filter((u: any) => u.status === 'active').length,
    admins: users.filter((u: any) => u.role === 'admin').length,
  };

  const columns = [
    { title: t('pages.users.username'), dataIndex: 'username', key: 'username', width: 120 },
    { title: t('pages.users.real_name'), dataIndex: 'real_name', key: 'real_name', width: 100 },
    { title: t('pages.users.phone'), dataIndex: 'phone', key: 'phone', width: 130 },
    { title: t('pages.users.email'), dataIndex: 'email', key: 'email', ellipsis: true },
    {
      title: t('pages.users.role'),
      dataIndex: 'role',
      key: 'role',
      width: 100,
      render: (role: string) => (
        <Tag color={roleColorMap[role]}>{roleTextMap[role] || role}</Tag>
      ),
    },
    { title: t('pages.users.team'), dataIndex: 'team_name', key: 'team_name', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={statusColorMap[status]}>{statusTextMap[status] || status}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (record: any) => (
        <Space size="small">
          <Button 
            icon={<EditOutlined />} 
            size="small" 
            onClick={() => {
              setSelectedUser(record);
              form.setFieldsValue(record);
              setModalVisible(true);
            }} 
          />
          <Button 
            icon={<LockOutlined />} 
            size="small" 
            onClick={() => {
              Modal.confirm({
                title: t('pages.users.reset_password'),
                content: t('pages.users.confirm_reset', { name: record.real_name || record.username }),
                onOk: () => message.success(t('pages.users.password_reset')),
              });
            }} 
          />
          <Popconfirm 
            title="确认删除?" 
            onConfirm={async () => {
              try {
                await userAPI.delete(record.id);
                message.success(t('pages.users.delete_success'));
                loadUsers();
              } catch {
                message.error(t('pages.users.delete_failed'));
              }
            }}
          >
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-container">
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic title={t('pages.users.total_count')} value={stats.total} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title={t('pages.users.active_count')} value={stats.active} valueStyle={{ color: '#34a853' }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title={t('pages.users.admin_count')} value={stats.admins} valueStyle={{ color: '#ff5a36' }} />
          </Card>
        </Col>
      </Row>

      <Card>
        {/* 筛选栏 */}
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder={t('pages.users.search_placeholder')}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Select value={roleFilter} onChange={setRoleFilter} style={{ width: 120 }}>
            <Select.Option value="all">{t('pages.users.filter_all_role')}</Select.Option>
            <Select.Option value="admin">{t('pages.users.role_admin')}</Select.Option>
            <Select.Option value="manager">{t('pages.users.role_manager')}</Select.Option>
            <Select.Option value="operator">{t('pages.users.role_operator')}</Select.Option>
            <Select.Option value="viewer">{t('pages.users.role_viewer')}</Select.Option>
          </Select>
          <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
            <Select.Option value="all">{t('pages.users.filter_all_status')}</Select.Option>
            <Select.Option value="active">{t('pages.users.status_active')}</Select.Option>
            <Select.Option value="inactive">{t('pages.users.status_inactive')}</Select.Option>
            <Select.Option value="locked">{t('pages.users.status_locked')}</Select.Option>
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            form.resetFields();
            setSelectedUser(null);
            setModalVisible(true);
          }}>
            {t('pages.users.add')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>{t('app.refresh')}</Button>
        </Space>

        <Table 
          dataSource={filteredUsers} 
          columns={columns} 
          rowKey="id" 
          loading={loading} 
          pagination={{ pageSize: 10, showTotal: (total) => t('app.total', { count: total }) }}
        />
      </Card>

      {/* 新增/编辑弹窗 */}
      <Modal 
        title={selectedUser ? t('pages.users.edit') : t('pages.users.add')} 
        open={modalVisible} 
        onCancel={() => setModalVisible(false)} 
        onOk={async () => {
          try {
            const values = await form.validateFields();
            try {
              if (selectedUser) {
                await userAPI.update(selectedUser.id, values);
                message.success(t('pages.users.update_success'));
              } else {
                await userAPI.create(values);
                message.success(t('pages.users.create_success'));
              }
              setModalVisible(false);
              form.resetFields();
              loadUsers();
            } catch {
              message.error(selectedUser ? t('pages.users.update_failed') : t('pages.users.create_failed'));
            }
          } catch {
            // 静默处理：表单校验失败由 antd 字段提示覆盖
          }
        }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="username" label={t('pages.users.username')} rules={[{ required: true, message: t('pages.users.username_required') }]}>
                <Input placeholder={t('pages.users.username_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="real_name" label={t('pages.users.real_name')} rules={[{ required: true, message: t('pages.users.name_required') }]}>
                <Input placeholder={t('pages.users.name_placeholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="phone" label={t('pages.users.phone')}>
                <Input placeholder={t('pages.users.phone_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label={t('pages.users.email')}>
                <Input placeholder={t('pages.users.email_placeholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="role" label={t('pages.users.role')} rules={[{ required: true }]}>
                <Select placeholder={t('pages.users.role_placeholder')}>
                  <Select.Option value="admin">{t('pages.users.role_admin')}</Select.Option>
                  <Select.Option value="manager">{t('pages.users.role_manager')}</Select.Option>
                  <Select.Option value="operator">{t('pages.users.role_operator')}</Select.Option>
                  <Select.Option value="viewer">{t('pages.users.role_viewer')}</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="team_id" label={t('pages.users.team')}>
                <Select placeholder={t('pages.users.team_placeholder')} allowClear>
                  <Select.Option value={1}>{t('pages.users.team_ops')}</Select.Option>
                  <Select.Option value={2}>{t('pages.users.team_tech')}</Select.Option>
                  <Select.Option value={3}>{t('pages.users.team_mgmt')}</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          {!selectedUser && (
            <Form.Item name="password" label={t('pages.users.password')} rules={[{ required: true, message: t('pages.users.password_required') }]}>
              <Input.Password placeholder={t('pages.users.password_placeholder')} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 用户详情弹窗 */}
      <Modal 
        title={t('pages.users.detail')} 
        open={detailVisible} 
        onCancel={() => setDetailVisible(false)} 
        footer={null} 
        width={700}
      >
        {selectedUser && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label={t('pages.users.username')}>{selectedUser.username}</Descriptions.Item>
            <Descriptions.Item label={t('pages.users.real_name')}>{selectedUser.real_name}</Descriptions.Item>
            <Descriptions.Item label={t('pages.users.phone')}>{selectedUser.phone}</Descriptions.Item>
            <Descriptions.Item label={t('pages.users.email')}>{selectedUser.email}</Descriptions.Item>
            <Descriptions.Item label={t('pages.users.role')}>
              <Tag color={roleColorMap[selectedUser.role]}>{roleTextMap[selectedUser.role]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('app.status')}>
              <Tag color={statusColorMap[selectedUser.status]}>{statusTextMap[selectedUser.status]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('pages.users.team')}>{selectedUser.team_name}</Descriptions.Item>
            <Descriptions.Item label={t('app.created_at')}>{selectedUser.created_at}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default UsersPage;
