/**
 * 天链V3 - 团队管理（平台管理核心页面）
 *
 * 三级架构：SaaS平台 → 运营公司（OPS_COMPANY）→ 运维团队（MAINTENANCE_TEAM）→ 光储充场站
 * 本页面：平台管理所有团队，按 TeamType 通过 URL query param ?type=xxx 区分
 *
 * 三个子页面通过 Tab 切换：
 * - 团队列表 /tenants → 表格视图，CRUD操作
 * - 团队数据 /tenants/data → 数据统计分析
 * - 团队账户 /tenants/accounts → 账户管理
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Tabs, Drawer, Modal, Form, Input, Select, InputNumber,
  Descriptions, Tag, Row, Col, Statistic, Badge, Table, Empty,
} from 'antd';
import {
  TeamOutlined, BarChartOutlined, UserOutlined,
} from '@ant-design/icons';
import { tenantAPI } from '../../api';
import { getStatusMap } from './utils';
import { useTenants } from './hooks/useTenants';
import TeamListView from './components/TeamListView';
import TeamDataView from './components/TeamDataView';
import TeamAccountsView from './components/TeamAccountsView';

// ==================== 主页面（Tab容器）====================

const TenantsPage: React.FC = () => {
  const {
    t,
    tenants,
    loading,
    modalVisible,
    setModalVisible,
    drawerVisible,
    setDrawerVisible,
    selectedTenant,
    setSelectedTenant,
    editingTenant,
    setEditingTenant,
    searchText,
    setSearchText,
    form,
    teamType,
    needsParentTeam,
    opsCompanies,
    getActiveTab,
    onTabChange,
    fetchTenants,
    fetchStats,
    openEdit,
    toggleStatus,
    handleDelete,
    handleSave,
  } = useTenants();

  // ---------- 成员列表（真实 API，卡eb81ca13：去除硬编码 mock） ----------
  const [members, setMembers] = useState<{ id: number; username: string; real_name: string | null; role: string; status: string }[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);

  const fetchMembers = useCallback(async (tenantId: number) => {
    setMembersLoading(true);
    try {
      const res = await tenantAPI.users(tenantId);
      const data = res.data;
      const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
      setMembers(list);
    } catch {
      setMembers([]);
    } finally {
      setMembersLoading(false);
    }
  }, []);

  useEffect(() => {
    if (drawerVisible && selectedTenant) {
      fetchMembers(selectedTenant.id);
    } else {
      setMembers([]);
    }
  }, [drawerVisible, selectedTenant, fetchMembers]);

  // ---------- 渲染 ----------

  const tabItems = [
    {
      key: 'list',
      label: <span><TeamOutlined /> {t('pages.tenants.team_list')}</span>,
      children: (
        <TeamListView
          tenants={tenants}
          loading={loading}
          searchText={searchText}
          needsParentTeam={needsParentTeam}
          onSearchChange={setSearchText}
          onRefresh={() => { fetchTenants(searchText); fetchStats(); }}
          onOpenCreate={() => { setEditingTenant(null); form.resetFields(); setModalVisible(true); }}
          onOpenEdit={openEdit}
          onToggleStatus={toggleStatus}
          onDelete={handleDelete}
          onViewDetail={(t) => { setSelectedTenant(t); setDrawerVisible(true); }}
        />
      ),
    },
    {
      key: 'data',
      label: <span><BarChartOutlined /> {t('pages.tenants.team_data')}</span>,
      children: (
        <TeamDataView
          tenants={tenants}
          loading={loading}
          onRefresh={() => { fetchTenants(); fetchStats(); }}
        />
      ),
    },
    {
      key: 'accounts',
      label: <span><UserOutlined /> {t('pages.tenants.team_accounts')}</span>,
      children: (
        <TeamAccountsView
          tenants={tenants}
          loading={loading}
          onRefresh={fetchTenants}
        />
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Tabs activeKey={getActiveTab()} onChange={onTabChange} items={tabItems} />
      </Card>

      {/* 团队详情 Drawer */}
      <Drawer title={selectedTenant?.name} open={drawerVisible} onClose={() => setDrawerVisible(false)} width={640}>
        {selectedTenant && (
          <Tabs defaultActiveKey="info">
            <Tabs.TabPane tab={t('pages.tenants.basic_info')} key="info">
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label={t('pages.tenants.team_name')}>{selectedTenant.name}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.code')}>{selectedTenant.code}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.contact')}>{selectedTenant.contact}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.phone')}>{selectedTenant.phone}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.email')}>{selectedTenant.email}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.address')}>{selectedTenant.address}</Descriptions.Item>
                {needsParentTeam && (
                  <Descriptions.Item label="所属运营公司">
                    {selectedTenant.parent_team_name || (selectedTenant.parent_team_id ? `#${selectedTenant.parent_team_id}` : <Tag>独立</Tag>)}
                  </Descriptions.Item>
                )}
                <Descriptions.Item label={t('app.status')}><Tag color={getStatusMap(t)[selectedTenant.status]?.color}>{getStatusMap(t)[selectedTenant.status]?.text}</Tag></Descriptions.Item>
                <Descriptions.Item label={t('app.created_at')}>{selectedTenant.created_at}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.expired_at')}>{selectedTenant.expired_at}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.station_quota')}>{selectedTenant.max_stations}</Descriptions.Item>
                <Descriptions.Item label={t('pages.tenants.device_quota')}>{selectedTenant.max_devices}</Descriptions.Item>
              </Descriptions>
            </Tabs.TabPane>
            <Tabs.TabPane tab={t('pages.tenants.usage_data')} key="data">
              <Row gutter={[16, 16]}>
                <Col span={12}><Card size="small"><Statistic title="站点数" value={selectedTenant.station_count} suffix={`/ ${selectedTenant.max_stations || '-'}`} /></Card></Col>
                <Col span={12}><Card size="small"><Statistic title={t('pages.tenants.devices_count')} value={selectedTenant.device_count} suffix={`/ ${selectedTenant.max_devices || '-'}`} /></Card></Col>
                <Col span={12}><Card size="small"><Statistic title="成员数" value={selectedTenant.member_count} /></Card></Col>
                <Col span={12}><Card size="small"><Statistic title="本月工单" value={selectedTenant.workorder_count} /></Card></Col>
                <Col span={12}><Card size="small"><Statistic title="本月告警" value={selectedTenant.alarm_count} valueStyle={{ color: selectedTenant.alarm_count > 0 ? '#ea4335' : undefined }} /></Card></Col>
                <Col span={12}><Card size="small"><Statistic title="API调用" value={selectedTenant.api_calls || 0} /></Card></Col>
              </Row>
            </Tabs.TabPane>
            <Tabs.TabPane tab={t('pages.tenants.member_management')} key="members">
              <Table
                dataSource={members}
                loading={membersLoading}
                locale={{ emptyText: <Empty description={t('pages.tenants.members_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                columns={[
                  { title: t('pages.tenants.real_name'), dataIndex: 'real_name', render: (v: string | null) => v || '-' },
                  { title: t('pages.tenants.account_name'), dataIndex: 'username' },
                  { title: '角色', dataIndex: 'role', render: (r: string) => <Tag>{r}</Tag> },
                  { title: '状态', dataIndex: 'status', render: (s: string) => <Badge status={s === 'active' ? 'success' : 'default'} /> },
                ]}
                rowKey="id" pagination={false} size="small"
              />
              <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>{t('pages.tenants.members_readonly_note')}</div>
            </Tabs.TabPane>
          </Tabs>
        )}
      </Drawer>

      {/* 新增/编辑 Modal */}
      <Modal title={editingTenant ? t('pages.tenants.edit') : t('pages.tenants.add')} open={modalVisible} onCancel={() => { setModalVisible(false); setEditingTenant(null); }} onOk={handleSave} width={600}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label={t('pages.tenants.team_name')} rules={[{ required: true }]}><Input placeholder={t('pages.tenants.name_placeholder')} /></Form.Item></Col>
            <Col span={12}><Form.Item name="code" label={t('pages.tenants.code')} rules={[{ required: true }]}><Input placeholder={t('pages.tenants.code_placeholder')} /></Form.Item></Col>
          </Row>
          {/* 运维团队表单：所属运营公司下拉（可选，留空=独立团队） */}
          {needsParentTeam && (
            <Form.Item name="parent_team_id" label="所属运营公司" tooltip="留空则为独立团队（不归属任何运营公司）">
              <Select
                allowClear
                placeholder="选择所属运营公司（可选）"
                options={opsCompanies.map(c => ({ label: c.name, value: c.id }))}
              />
            </Form.Item>
          )}
          <Row gutter={16}>
            <Col span={12}><Form.Item name="contact" label={t('pages.tenants.contact')} rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="phone" label={t('pages.tenants.phone')}><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="email" label={t('pages.tenants.email')}><Input /></Form.Item>
          <Form.Item name="address" label={t('pages.tenants.address')}><Input /></Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="max_stations" label={t('pages.tenants.station_quota')} initialValue={10}><InputNumber min={1} max={1000} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="max_devices" label={t('pages.tenants.device_quota')} initialValue={100}><InputNumber min={1} max={10000} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Form.Item name="expired_at" label={t('pages.tenants.expired_at')}><Input type="date" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TenantsPage;
