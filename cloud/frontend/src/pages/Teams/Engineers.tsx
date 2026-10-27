/**
 * 天链 V3 - 独立工程师管理页面（SPEC 第3章）
 * 列表表格 + 筛选 + 添加/编辑弹窗 + 删除确认
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Card, Button, Space, Tag, Modal, Form, Input, Select, message,
  Popconfirm, Tooltip, Row, Col, Badge,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  SearchOutlined, ToolOutlined,
} from '@ant-design/icons';
import { teamAPI, engineerAPI } from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

const levelOptions = [
  { value: 'junior', label: '初级工程师', color: 'green' },
  { value: 'middle', label: '中级工程师', color: 'blue' },
  { value: 'senior', label: '高级工程师', color: 'orange' },
];

const levelColorMap: Record<string, string> = {
  junior: 'green',
  middle: 'blue',
  senior: 'orange',
};

const levelLabelMap: Record<string, string> = {
  junior: '初级',
  middle: '中级',
  senior: '高级',
};

const statusColorMap: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  suspended: 'red',
};

const statusLabelMap: Record<string, string> = {
  active: '启用',
  inactive: '停用',
  suspended: '冻结',
};

const EngineersPage: React.FC = () => {
  const [engineers, setEngineers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [teams, setTeams] = useState<any[]>([]);

  // 筛选
  const [filterTeamId, setFilterTeamId] = useState<number | undefined>();
  const [filterLevel, setFilterLevel] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();

  // 弹窗
  const [modalVisible, setModalVisible] = useState(false);
  const [editingEngineer, setEditingEngineer] = useState<any>(null);
  const [form] = Form.useForm();

  /* ── 加载团队列表 ── */
  const loadTeams = useCallback(async () => {
    try {
      const res = await teamAPI.list();
      const data = res.data?.data || res.data;
      setTeams(data?.items || data || []);
    } catch {
      // 静默处理
    }
  }, []);

  useEffect(() => { loadTeams(); }, [loadTeams]);

  /* ── 加载工程师列表 ── */
  const loadEngineers = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 604c1e16: /engineers page_size 契约 le=100, 手拼 200 必 422 → fetchAllPages 循环拉全量
      const params: Record<string, unknown> = {};
      if (filterTeamId) params.team_id = filterTeamId;
      if (filterLevel) params.level = filterLevel;
      if (filterStatus) params.status = filterStatus;

      const items = await fetchAllPages(engineerAPI.list, params);
      setEngineers(items);
    } catch (err: any) {
      if (err?.response?.status !== 401) {
        message.error('加载工程师列表失败');
      }
    }
    setLoading(false);
  }, [filterTeamId, filterLevel, filterStatus]);

  useEffect(() => { loadEngineers(); }, [loadEngineers]);

  /* ── 获取团队名称 ── */
  const getTeamName = (teamId: number | null | undefined): string => {
    if (!teamId) return '-';
    const team = teams.find((t: any) => t.id === teamId);
    return team?.name || `团队${teamId}`;
  };

  /* ── CRUD 操作 ── */
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload: Record<string, unknown> = {
        name: values.name,
        phone: values.phone,
        level: values.level,
        team_id: values.team_id || null,
      };

      if (editingEngineer) {
        // 更新
        if (values.password) {
          payload.password = values.password;
        }
        if (values.status !== undefined) {
          payload.status = values.status;
        }
        await engineerAPI.update(editingEngineer.id, payload);
        message.success('工程师信息已更新');
      } else {
        // 创建
        payload.password = values.password || 'default123456';
        await engineerAPI.create(payload);
        message.success('工程师已创建');
      }

      setModalVisible(false);
      form.resetFields();
      loadEngineers();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || '操作失败';
      message.error(msg);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await engineerAPI.delete(id);
      message.success('工程师已删除');
      loadEngineers();
    } catch {
      message.error('删除失败');
    }
  };

  /* ── 统计 ── */
  const stats = {
    total: engineers.length,
    junior: engineers.filter((e: any) => e.level === 'junior').length,
    middle: engineers.filter((e: any) => e.level === 'middle').length,
    senior: engineers.filter((e: any) => e.level === 'senior').length,
    active: engineers.filter((e: any) => e.status === 'active' || !e.status).length,
  };

  /* ── 表格列 ── */
  const columns = [
    {
      title: '姓名', dataIndex: 'name', key: 'name', width: 120, ellipsis: true,
      render: (name: string) => <span style={{ fontWeight: 500 }}>{name}</span>,
    },
    {
      title: '手机号', dataIndex: 'phone', key: 'phone', width: 130,
      render: (phone: string) => phone || '-',
    },
    {
      title: '等级', dataIndex: 'level', key: 'level', width: 100,
      render: (level: string) => (
        <Tag color={levelColorMap[level] || 'default'}>
          {levelLabelMap[level] || level}
        </Tag>
      ),
    },
    {
      title: '所属团队', dataIndex: 'team_id', key: 'team_id', width: 130,
      render: (teamId: number) => getTeamName(teamId),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {statusLabelMap[status] || status}
        </Tag>
      ),
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: unknown, record: any) => (
        <Space size={4}>
          <Tooltip title="编辑">
            <Button
              icon={<EditOutlined />} size="small"
              onClick={() => {
                setEditingEngineer(record);
                form.setFieldsValue({
                  name: record.name,
                  phone: record.phone,
                  level: record.level,
                  team_id: record.team_id,
                  status: record.status,
                  password: undefined,
                });
                setModalVisible(true);
              }}
            />
          </Tooltip>
          <Popconfirm title="确认删除该工程师？" onConfirm={() => handleDelete(record.id)}>
            <Tooltip title="删除">
              <Button icon={<DeleteOutlined />} size="small" danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24, background: '#faf5f4', minHeight: '100vh' }}>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ff5a36' }}>{stats.total}</div>
            <div style={{ color: '#999' }}>工程师总数</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#34a853' }}>{stats.junior}</div>
            <div style={{ color: '#999' }}>初级</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1d4ed8' }}>{stats.middle}</div>
            <div style={{ color: '#999' }}>中级</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ea580c' }}>{stats.senior}</div>
            <div style={{ color: '#999' }}>高级</div>
          </Card>
        </Col>
      </Row>

      {/* 工程师列表 */}
      <Card
        title={
          <Space>
            <ToolOutlined style={{ color: '#ff5a36' }} />
            <span>工程师管理</span>
            <Badge count={stats.active} style={{ backgroundColor: '#34a853' }} />
          </Space>
        }
        extra={
          <Space size={8}>
            <Select
              placeholder="所属团队"
              allowClear
              style={{ width: 140 }}
              value={filterTeamId}
              onChange={(v) => setFilterTeamId(v)}
              size="small"
            >
              {teams.map((t: any) => (
                <Select.Option key={t.id} value={t.id}>{t.name}</Select.Option>
              ))}
            </Select>
            <Select
              placeholder="等级筛选"
              allowClear
              style={{ width: 120 }}
              value={filterLevel}
              onChange={(v) => setFilterLevel(v)}
              size="small"
            >
              {levelOptions.map((opt) => (
                <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
              ))}
            </Select>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 100 }}
              value={filterStatus}
              onChange={(v) => setFilterStatus(v)}
              size="small"
            >
              <Select.Option value="active">启用</Select.Option>
              <Select.Option value="inactive">停用</Select.Option>
              <Select.Option value="suspended">冻结</Select.Option>
            </Select>
            <Button
              type="primary" icon={<PlusOutlined />} size="small"
              onClick={() => {
                setEditingEngineer(null);
                form.resetFields();
                form.setFieldsValue({ level: 'junior' });
                setModalVisible(true);
              }}
            >
              添加工程师
            </Button>
            <Button icon={<ReloadOutlined />} size="small" onClick={loadEngineers} />
          </Space>
        }
      >
        <Table
          dataSource={engineers}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 名工程师` }}
          size="small"
          scroll={{ x: 900 }}
        />
      </Card>

      {/* 添加/编辑弹窗 */}
      <Modal
        title={editingEngineer ? '编辑工程师' : '添加工程师'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
        }}
        onOk={handleSave}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name" label="姓名"
                rules={[{ required: true, message: '请输入姓名' }]}
              >
                <Input placeholder="工程师姓名" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="手机号">
                <Input placeholder="手机号" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="password"
            label="密码"
            rules={editingEngineer ? [] : [{ required: true, message: '请输入密码', min: 6 }]}
            extra={editingEngineer ? '留空则不修改密码' : ''}
          >
            <Input.Password placeholder={editingEngineer ? '留空不修改' : '设置密码（最少6位）'} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="level" label="等级"
                rules={[{ required: true, message: '请选择等级' }]}
              >
                <Select>
                  {levelOptions.map((opt) => (
                    <Select.Option key={opt.value} value={opt.value}>
                      <Space>
                        <span style={{
                          display: 'inline-block', width: 8, height: 8,
                          borderRadius: '50%', background: opt.color,
                        }} />
                        {opt.label}
                      </Space>
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="team_id" label="所属团队">
                <Select placeholder="选择团队" allowClear>
                  {teams.map((t: any) => (
                    <Select.Option key={t.id} value={t.id}>{t.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          {editingEngineer && (
            <Form.Item name="status" label="状态">
              <Select>
                <Select.Option value="active">启用</Select.Option>
                <Select.Option value="inactive">停用</Select.Option>
                <Select.Option value="suspended">冻结</Select.Option>
              </Select>
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default EngineersPage;
