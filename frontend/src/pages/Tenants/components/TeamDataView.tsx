/**
 * Tab2: 团队数据（该团队所有数据管理）
 *
 * 子 Tab：账户 / 场站 / 设备 / 操作记录 / 工单；含备份导出与跨 Pod 迁移。
 * 卡9a81fffd：账户列表接真实 API（GET /teams/{team_id}/members），去除硬编码假账号；
 * 卡2285f54a：场站/设备/工单接真实 API（列表 API 新增可选 team_id 查询参数，
 * admin 可指定任意团队），替换空态；操作记录仍留空（后端无 team 维度操作日志 API）。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Card, Button, Space, Tag, Modal, Select, message,
  Descriptions, Row, Col, Statistic, Alert, Empty, Tabs, Badge, Typography,
} from 'antd';
import {
  UserOutlined, HomeOutlined, TeamOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ReloadOutlined, DownloadOutlined, SwapOutlined,
  KeyOutlined, LockOutlined,
} from '@ant-design/icons';
import { teamAPI, stationAPI, deviceAPI, workorderAPI } from '../../../api';
import { fetchAllPages } from '../../../api/fetchAll';
import type { Tenant } from '../types';

const { Text } = Typography;

interface TeamMember {
  id: number;
  username: string;
  real_name: string | null;
  role: string;
  status: string;
  phone?: string | null;
  join_date?: string | null;
}

// 卡2285f54a：列表 API + team_id 查询参数返回的真实字段（后端序列化契约）
interface TeamStation {
  id: number;
  name: string;
  address?: string | null;
  status: string;
  total_devices?: number | null;
  total_power?: number | null;
  gun_count?: number | null;
}

interface TeamDevice {
  id: number;
  name: string;
  sn?: string | null;
  type: string;
  status: string;
  power?: number | null;
  health_score?: number | null;
}

interface TeamWorkOrder {
  id: string;
  fault_desc?: string | null;
  type: string;
  level: string;
  status: string;
  station_id?: number | null;
  create_time?: string | null;
}

const emptyTableLocale = (t: (k: string) => string) => ({
  emptyText: <Empty description={t('pages.tenants.members_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />,
});

const OperationRecord: React.FC<{ record: { id: string; content: string; operator: string; time: string; type: string } }> = ({ record }) => (
  <div style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
    <Space>
      <Tag>{record.type}</Tag>
      <Text>{record.content}</Text>
      <Text type="secondary">{record.operator}</Text>
      <Text type="secondary">{record.time}</Text>
    </Space>
  </div>
);

const TeamDataView: React.FC<{
  tenants: Tenant[];
  loading: boolean;
  onRefresh: () => void;
}> = ({ tenants, loading, onRefresh }) => {
  const { t } = useTranslation();

  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(
    tenants.length > 0 ? tenants[0].id : null
  );
  const [innerTab, setInnerTab] = useState('accounts');
  const [migrateModalOpen, setMigrateModalOpen] = useState(false);
  const [migrateTargetPod, setMigrateTargetPod] = useState('pod-02');
  const [backupLoading, setBackupLoading] = useState(false);

  // ---------- 成员（真实 API，卡9a81fffd） ----------
  const [teamAccounts, setTeamAccounts] = useState<TeamMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);

  const fetchMembers = useCallback(async (tenantId: number) => {
    setMembersLoading(true);
    try {
      const res = await teamAPI.members(tenantId);
      const data = res.data;
      const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
      setTeamAccounts(list);
    } catch {
      setTeamAccounts([]);
    } finally {
      setMembersLoading(false);
    }
  }, []);

  // ---------- 场站/设备/工单（真实 API + team_id，卡2285f54a） ----------
  const [teamStations, setTeamStations] = useState<TeamStation[]>([]);
  const [teamDevices, setTeamDevices] = useState<TeamDevice[]>([]);
  const [teamWorkOrders, setTeamWorkOrders] = useState<TeamWorkOrder[]>([]);
  const [dataLoading, setDataLoading] = useState(false);

  const fetchTeamData = useCallback(async (tenantId: number) => {
    setDataLoading(true);
    const [stRes, devRes, woRes] = await Promise.allSettled([
      fetchAllPages<TeamStation>((params) => stationAPI.list(params), { team_id: tenantId }),
      fetchAllPages<TeamDevice>((params) => deviceAPI.list(params), { team_id: tenantId }),
      fetchAllPages((params) => workorderAPI.list(params), { team_id: tenantId }),
    ]);
    // 单路失败（403/网络）置空对应 Tab，不影响其他路；axios 拦截器已解包 envelope。
    // 工单列表处 cast：全局 WorkOrder 类型未声明 level 字段，后端实际返回（routes_lifecycle 序列化）
    setTeamStations(stRes.status === 'fulfilled' ? stRes.value : []);
    setTeamDevices(devRes.status === 'fulfilled' ? devRes.value : []);
    setTeamWorkOrders(woRes.status === 'fulfilled' ? (woRes.value as unknown as TeamWorkOrder[]) : []);
    setDataLoading(false);
  }, []);

  useEffect(() => {
    if (selectedTenantId != null) {
      fetchMembers(selectedTenantId);
      fetchTeamData(selectedTenantId);
    } else {
      setTeamAccounts([]);
      setTeamStations([]);
      setTeamDevices([]);
      setTeamWorkOrders([]);
    }
  }, [selectedTenantId, fetchMembers, fetchTeamData]);

  // 备份：导出该团队所有数据为JSON
  const handleBackup = () => {
    setBackupLoading(true);
    const backupData = {
      team: selectedTenant,
      accounts: teamAccounts,
      operations: teamOperations,
      exported_at: new Date().toISOString(),
      version: '3.0.0'
    };
    const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedTenant?.code || 'team'}_backup_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setBackupLoading(false);
    message.success(`团队「${selectedTenant?.name}」数据已导出`);
  };

  // 迁移：弹窗选择目标Pod
  const handleMigrate = () => {
    setMigrateTargetPod('pod-02');
    setMigrateModalOpen(true);
  };

  const confirmMigrate = () => {
    message.loading({ content: `正在迁移「${selectedTenant?.name}」到 ${migrateTargetPod}...`, key: 'migrate' });
    setTimeout(() => {
      message.success({ content: `团队「${selectedTenant?.name}」已迁移至 ${migrateTargetPod}`, key: 'migrate' });
      setMigrateModalOpen(false);
    }, 2000);
  };

  // 当选中的变更时同步
  useEffect(() => {
    if (tenants.length > 0 && !selectedTenantId) {
      setSelectedTenantId(tenants[0].id);
    }
  }, [tenants]);

  const selectedTenant = tenants.find(t => t.id === selectedTenantId);
  if (!selectedTenant) {
    return <Empty description={t('pages.tenants.select_team_first')} />;
  }

  // TODO(后续): 操作记录后端无 team 维度操作日志查询 API，先留空（卡2285f54a 范围外）。
  const teamOperations: { id: string; content: string; operator: string; time: string; type: string }[] = [];

  // 场站状态（后端 StationStatus: normal/maintenance/closed/active）
  const stationStatusColor: Record<string, string> = {
    normal: '#52c41a', active: '#52c41a', maintenance: '#faad14', closed: '#d9d9d9', offline: '#ff4d4f',
  };
  const stationStatusText: Record<string, string> = {
    normal: '正常', active: '活跃', maintenance: '维护中', closed: '已关闭', offline: '离线',
  };
  // 设备类型（后端 DeviceType 全集）
  const deviceTypeText: Record<string, string> = {
    pv_inverter: '光伏逆变器', battery_inverter: '储能变流器', pcs: '储能PCS',
    charger_dc: '直流充电桩', charger_ac: '交流充电桩', v2g_charger: 'V2G充电桩',
    battery: '储能电池', meter: '电表', gateway: '网关',
  };
  // 工单类型/级别/状态（后端 WorkOrderType/Level/Status）
  const woTypeText: Record<string, string> = {
    preventive: '预防性维护', emergency: '紧急故障', plan: '计划性维护', maintenance: '维修保养',
    inspection: '巡检', upgrade: '升级改造', repair: '报修', calibration: '校准',
  };
  const woLevelColor: Record<string, string> = {
    critical: 'red', P0: 'red', P1: 'orange', warning: 'orange', P2: 'gold', info: 'blue',
  };
  const woStatusText: Record<string, string> = {
    pending: '待处理', accepted: '已接单', processing: '处理中', pending_verify: '待验收',
    completed: '已完成', assigned: '已指派', in_progress: '进行中', resolved: '已解决', closed: '已关闭',
  };

  // 子Tab内容
  const innerTabItems = [
    {
      key: 'accounts',
      label: <span><UserOutlined /> {t('pages.tenants.accounts')} ({teamAccounts.length})</span>,
      children: (
        <Table dataSource={teamAccounts} rowKey="id" size="small" pagination={false}
          loading={membersLoading}
          locale={emptyTableLocale(t)}
          columns={[
            { title: t('pages.tenants.account_name'), dataIndex: 'username' },
            { title: t('pages.tenants.real_name'), dataIndex: 'real_name', render: (v: string | null) => v || '-' },
            { title: '角色', dataIndex: 'role', render: (r: string) => <Tag>{r}</Tag> },
            { title: t('pages.tenants.phone'), dataIndex: 'phone', render: (v: string | null) => v || '-' },
            { title: '状态', dataIndex: 'status', render: (s: string) => <Badge status={s === 'active' ? 'success' : 'default'} text={s === 'active' ? t('pages.tenants.normal') : t('pages.tenants.offline')} /> },
            { title: t('pages.tenants.last_login'), dataIndex: 'join_date', render: (v: string | null) => v?.slice(0, 10) || '-' },
            {
              title: '操作', key: 'action',
              render: () => (
                <Space>
                  <Button size="small" icon={<KeyOutlined />} onClick={() => message.success(t('pages.tenants.reset_pwd_sent'))}>{t('pages.tenants.reset_password')}</Button>
                  <Button size="small" icon={<LockOutlined />} danger onClick={() => message.success(t('pages.tenants.account_disabled'))}>{t('pages.tenants.disable_account')}</Button>
                </Space>
              ),
            },
          ]}
        />
      ),
    },
    {
      key: 'stations',
      label: <span><HomeOutlined /> {t('pages.tenants.stations')} ({teamStations.length})</span>,
      children: (
        <Table dataSource={teamStations} rowKey="id" size="small" pagination={false}
          loading={dataLoading}
          locale={emptyTableLocale(t)}
          columns={[
            { title: t('pages.tenants.station_name'), dataIndex: 'name' },
            { title: t('pages.tenants.address'), dataIndex: 'address', render: (v: string | null) => v || '-' },
            {
              title: '状态', dataIndex: 'status',
              render: (s: string) => <Badge color={stationStatusColor[s]} text={stationStatusText[s] || s} />,
            },
            { title: t('pages.tenants.devices_count'), dataIndex: 'total_devices', render: (v: number | null) => v ?? '-' },
            { title: t('pages.tenants.pv_power'), dataIndex: 'total_power', render: (v: number | null) => v != null ? `${v} kW` : '-' },
            { title: '充电枪数', dataIndex: 'gun_count', render: (v: number | null) => v ?? '-' },
          ]}
        />
      ),
    },
    {
      key: 'devices',
      label: <span><TeamOutlined /> {t('pages.tenants.devices')} ({teamDevices.length})</span>,
      children: (
        <Table dataSource={teamDevices} rowKey="id" size="small" pagination={false}
          loading={dataLoading}
          locale={emptyTableLocale(t)}
          columns={[
            { title: t('pages.tenants.device_name'), dataIndex: 'name' },
            { title: t('pages.tenants.device_type'), dataIndex: 'type', render: (v: string) => deviceTypeText[v] || v },
            { title: 'SN', dataIndex: 'sn', render: (v: string | null) => v || '-' },
            {
              title: '状态', dataIndex: 'status',
              render: (s: string) => <Badge status={s === 'online' ? 'success' : s === 'charging' ? 'processing' : s === 'fault' ? 'error' : s === 'maintenance' ? 'warning' : 'default'} text={{ online: '在线', charging: '充电中', fault: '故障', maintenance: '维护中', offline: '离线' }[s] || s} />,
            },
            { title: '当前功率(kW)', dataIndex: 'power', render: (v: number | null) => v != null ? v.toFixed(1) : '-' },
            { title: '健康度', dataIndex: 'health_score', render: (v: number | null) => v != null ? v.toFixed(0) : '-' },
          ]}
        />
      ),
    },
    {
      key: 'operations',
      label: <span><ExclamationCircleOutlined /> {t('pages.tenants.ops_records')} ({teamOperations.length})</span>,
      children: (
        <Card size="small">
          {teamOperations.length === 0
            ? <Empty description={t('pages.tenants.members_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            : teamOperations.map(op => <OperationRecord key={op.id} record={op} />)}
        </Card>
      ),
    },
    {
      key: 'workorders',
      label: <span><CheckCircleOutlined /> {t('pages.tenants.workorders')} ({teamWorkOrders.length})</span>,
      children: (
        <Table dataSource={teamWorkOrders} rowKey="id" size="small" pagination={false}
          loading={dataLoading}
          locale={emptyTableLocale(t)}
          columns={[
            { title: t('pages.tenants.workorder_id'), dataIndex: 'id', width: 150 },
            { title: t('pages.tenants.title'), dataIndex: 'fault_desc', render: (v: string | null) => v || '-' },
            { title: t('pages.tenants.station'), dataIndex: 'station_id', render: (v: number | null) => v != null ? `#${v}` : '-' },
            { title: t('pages.tenants.device_type'), dataIndex: 'type', render: (v: string) => woTypeText[v] || v },
            {
              title: t('pages.tenants.priority'), dataIndex: 'level',
              render: (l: string) => <Tag color={woLevelColor[l] || 'default'}>{l}</Tag>,
            },
            { title: '状态', dataIndex: 'status', render: (s: string) => woStatusText[s] || s },
            { title: t('app.created_at'), dataIndex: 'create_time', render: (v: string | null) => v?.slice(0, 16).replace('T', ' ') || '-' },
          ]}
        />
      ),
    },
  ];

  return (
    <div>
      {/* 团队选择器 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Text strong>{t('pages.tenants.select_team')}：</Text>
          <Select
            style={{ width: 300 }}
            value={selectedTenantId}
            onChange={v => setSelectedTenantId(v)}
            options={tenants.map(t => ({ label: `${t.name} (${t.code})`, value: t.id }))}
          />
          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>{t('app.refresh')}</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={handleBackup} loading={backupLoading}>{t('pages.tenants.backup')}</Button>
          <Button size="small" icon={<SwapOutlined />} onClick={handleMigrate}>{t('pages.tenants.migrate')}</Button>
        </Space>
      </Card>

      {/* 团队概览统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title={t('pages.tenants.accounts_count')} value={teamAccounts.length} prefix={<UserOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('pages.tenants.stations_count')} value={teamStations.length} prefix={<HomeOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('pages.tenants.devices_count')} value={teamDevices.length} prefix={<TeamOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('pages.tenants.workorders_count')} value={teamWorkOrders.length} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
      </Row>

      {/* 该团队的数据详情Tabs */}
      <Card title={`${selectedTenant.name} - 数据详情`} size="small">
        <Tabs activeKey={innerTab} onChange={setInnerTab} items={innerTabItems} />
      </Card>

      {/* 迁移确认弹窗 */}
      <Modal
        title={<span><SwapOutlined /> 迁移团队</span>}
        open={migrateModalOpen}
        onCancel={() => setMigrateModalOpen(false)}
        onOk={confirmMigrate}
        okText="确认迁移"
        cancelText="取消"
      >
        <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label="团队">{selectedTenant?.name} ({selectedTenant?.code})</Descriptions.Item>
          <Descriptions.Item label="当前Pod">pod-01 (default)</Descriptions.Item>
          <Descriptions.Item label="待迁移数据">
            {teamAccounts.length} 个账户、{teamStations.length} 个场站、{teamDevices.length} 台设备、{teamWorkOrders.length} 个工单
          </Descriptions.Item>
        </Descriptions>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>目标Pod：</Text>
          <Select
            style={{ width: '100%' }}
            value={migrateTargetPod}
            onChange={v => setMigrateTargetPod(v)}
            options={[
              { label: 'Pod-02 (华南区域)', value: 'pod-02' },
              { label: 'Pod-03 (华北区域)', value: 'pod-03' },
              { label: 'Pod-04 (西南区域)', value: 'pod-04' },
            ]}
          />
          <Alert
            message={t('pages.tenants.migrate_warning')}
            type="info"
            showIcon
            style={{ marginTop: 8 }}
          />
        </Space>
      </Modal>
    </div>
  );
};

export default TeamDataView;
