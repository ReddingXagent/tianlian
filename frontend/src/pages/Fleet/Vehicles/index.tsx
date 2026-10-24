/**
 * 车队 - 车辆管理页面
 *
 * 功能：车辆列表 / 搜索+状态筛选 / 绑定新车 / 详情抽屉 / 状态变更 / 解绑
 * API（企业维度）:
 *   GET    /enterprises/{eid}/vehicles
 *   POST   /enterprises/{eid}/vehicles            （绑定，详见 VehicleCreate）
 *   DELETE /enterprises/{eid}/vehicles/{id}       （解绑）
 *   PATCH  /enterprises/{eid}/vehicles/{id}       （状态变更，后端待实现）
 *
 * 说明：后端车辆接口为企业维度，页面默认取企业列表第一个企业作为当前企业。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Input, Select, Space, message, Popconfirm,
  Statistic, Row, Col, Dropdown, Empty,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, CarOutlined,
  DeleteOutlined, DownOutlined, EyeOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';
import VehicleCreate, { DriverOption } from './VehicleCreate';
import VehicleDetail from './VehicleDetail';

/* ── 类型 ── */
export interface Vehicle {
  id: number;
  enterprise_id?: number;
  plate_number: string;
  vin?: string;
  brand?: string;
  model?: string;
  driver_name?: string;
  driver_phone?: string;
  status: string;
  approval_status?: string;
  confirmed_at?: string;
  confirmed_by?: string;
  created_at?: string;
  updated_at?: string;
}

interface EnterpriseLite {
  id: number;
  name: string;
}

/* ── 常量 ── */
const STATUS_COLORS: Record<string, string> = {
  active: 'green', maintenance: 'orange', retired: 'red', inactive: 'default',
};
const STATUS_TEXT: Record<string, string> = {
  active: '在役', maintenance: '维修', retired: '退役', inactive: '停用',
};
const STATUS_OPTIONS = [
  { value: 'active', label: '在役' },
  { value: 'maintenance', label: '维修' },
  { value: 'retired', label: '退役' },
];

/* ── 确认状态 ── */
const APPROVAL_COLORS: Record<string, string> = {
  pending: 'gold', confirmed: 'green', rejected: 'red',
};
const APPROVAL_TEXT: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', rejected: '已拒绝',
};
const APPROVAL_OPTIONS = [
  { value: 'pending', label: '待确认' },
  { value: 'confirmed', label: '已确认' },
  { value: 'rejected', label: '已拒绝' },
];

/** 按当前状态推导可变更的下一个状态 */
const transitions = (status?: string): { status: string; label: string; danger?: boolean }[] => {
  switch (status) {
    case 'active':
      return [
        { status: 'maintenance', label: '转为维修' },
        { status: 'retired', label: '转为退役', danger: true },
      ];
    case 'maintenance':
      return [
        { status: 'active', label: '恢复在役' },
        { status: 'retired', label: '转为退役', danger: true },
      ];
    case 'retired':
    case 'inactive':
      return [{ status: 'active', label: '恢复在役' }];
    default:
      return [];
  }
};

/* ── 组件 ── */
const FleetVehiclesPage: React.FC = () => {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [approvalFilter, setApprovalFilter] = useState<string | undefined>(undefined);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);

  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailVehicle, setDetailVehicle] = useState<Vehicle | null>(null);
  // 受控状态变更确认（列表 Dropdown 触发）
  const [statusConfirm, setStatusConfirm] = useState<{ vehicle: Vehicle; status: string; label: string } | null>(null);

  /* ── 数据加载 ── */
  const loadEnterprises = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/enterprises');
      const items: EnterpriseLite[] = Array.isArray(data) ? data : (data as any)?.items || [];
      setEnterprises(items);
      if (items.length && currentEid === null) setCurrentEid(items[0].id);
    } catch {
      setEnterprises([]);
    }
  }, [currentEid]);

  const loadDrivers = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/drivers');
      const items = Array.isArray(data) ? data : (data as any)?.items || [];
      setDrivers(items.map((d: any) => ({ id: d.id, name: d.name, phone: d.phone })));
    } catch {
      setDrivers([]);
    }
  }, []);

  const loadVehicles = useCallback(async () => {
    if (!currentEid) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/enterprises/${currentEid}/vehicles`);
      const items = Array.isArray(data) ? data : (data as any)?.items || [];
      setVehicles(items);
    } catch {
      setVehicles([]);
    } finally {
      setLoading(false);
    }
  }, [currentEid]);

  useEffect(() => { loadEnterprises(); loadDrivers(); }, [loadEnterprises, loadDrivers]);
  useEffect(() => { if (currentEid) loadVehicles(); }, [currentEid, loadVehicles]);

  /* ── 状态变更 / 解绑 ── */
  const handleStatusChange = async (vehicle: Vehicle, status: string) => {
    if (!currentEid) return;
    try {
      await api.patch(`/enterprises/${currentEid}/vehicles/${vehicle.id}`, { status });
      message.success('状态已更新');
      // 同步刷新列表与详情
      loadVehicles();
      setDetailVehicle(prev => (prev && prev.id === vehicle.id ? { ...prev, status } : prev));
    } catch (err: any) {
      message.error('状态更新失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleUnbind = async (id: number) => {
    if (!currentEid) return;
    try {
      await api.delete(`/enterprises/${currentEid}/vehicles/${id}`);
      message.success('车辆已解绑');
      loadVehicles();
    } catch (err: any) {
      message.error('解绑失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 确认 / 拒绝 / 批量确认 ── */
  const handleConfirm = async (id: number) => {
    if (!currentEid) return;
    try {
      await api.post(`/enterprises/${currentEid}/vehicles/${id}/confirm`);
      message.success('车辆已确认');
      loadVehicles();
    } catch (err: any) {
      message.error('确认失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleReject = async (id: number) => {
    if (!currentEid) return;
    try {
      await api.post(`/enterprises/${currentEid}/vehicles/${id}/reject`, {});
      message.success('车辆已拒绝');
      loadVehicles();
    } catch (err: any) {
      message.error('拒绝失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleBatchConfirm = async () => {
    if (!currentEid || selectedRowKeys.length === 0) return;
    try {
      const { data } = await api.post(`/enterprises/${currentEid}/vehicles/batch-confirm`, {
        vehicle_ids: selectedRowKeys,
      });
      const result = data?.data || data;
      message.success(`批量确认完成: ${result.total_confirmed}辆确认, ${result.skipped_ids?.length || 0}辆跳过`);
      setSelectedRowKeys([]);
      loadVehicles();
    } catch (err: any) {
      message.error('批量确认失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 详情 ── */
  const openDetail = (vehicle: Vehicle) => {
    setDetailVehicle(vehicle);
    setDetailOpen(true);
  };

  /* ── 筛选 ── */
  const filtered = vehicles.filter(v =>
    (!search || v.plate_number?.toLowerCase().includes(search.toLowerCase())
      || v.vin?.toLowerCase().includes(search.toLowerCase())
      || v.driver_name?.toLowerCase().includes(search.toLowerCase()))
    && (!statusFilter || v.status === statusFilter)
    && (!approvalFilter || v.approval_status === approvalFilter)
  );

  /* ── 统计 ── */
  const stats = {
    total: vehicles.length,
    active: vehicles.filter(v => v.status === 'active').length,
    maintenance: vehicles.filter(v => v.status === 'maintenance').length,
    retired: vehicles.filter(v => v.status === 'retired').length,
    pending: vehicles.filter(v => v.approval_status === 'pending').length,
    confirmed: vehicles.filter(v => v.approval_status === 'confirmed').length,
    rejected: vehicles.filter(v => v.approval_status === 'rejected').length,
  };

  const fmtDate = (v?: string) => (v ? v.split('T')[0] : '-');

  const columns = [
    {
      title: '车牌号', dataIndex: 'plate_number', key: 'plate_number', width: 120,
      render: (v: string) => <Tag color="blue" style={{ fontSize: 13 }}>{v}</Tag>,
    },
    {
      title: '品牌车型', key: 'brand_model', width: 140, ellipsis: true,
      render: (_: unknown, r: Vehicle) => [r.brand, r.model].filter(Boolean).join(' ') || '-',
    },
    { title: 'VIN码', dataIndex: 'vin', key: 'vin', width: 160, ellipsis: true, render: (v: string) => v ? <code style={{ fontSize: 11 }}>{v}</code> : '-' },
    {
      title: '绑定司机', key: 'driver', width: 130, ellipsis: true,
      render: (_: unknown, r: Vehicle) => r.driver_name ? `${r.driver_name}${r.driver_phone ? ` (${r.driver_phone})` : ''}` : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={STATUS_COLORS[v] || 'default'}>{STATUS_TEXT[v] || v}</Tag>,
    },
    {
      title: '确认', dataIndex: 'approval_status', key: 'approval_status', width: 80,
      render: (v: string) => <Tag color={APPROVAL_COLORS[v] || 'default'}>{APPROVAL_TEXT[v] || v || '待确认'}</Tag>,
    },
    { title: '绑定时间', dataIndex: 'created_at', key: 'created_at', width: 110, render: (v: string) => fmtDate(v) },
    {
      title: '操作', key: 'action', width: 320,
      render: (_: unknown, r: Vehicle) => (
        <Space size={4} wrap onClick={e => e.stopPropagation()}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(r)}>详情</Button>
          {r.approval_status === 'pending' && (
            <>
              <Button size="small" type="primary" style={{ background: '#52c41a', borderColor: '#52c41a' }}
                onClick={() => handleConfirm(r.id)}>确认</Button>
              <Button size="small" danger onClick={() => handleReject(r.id)}>拒绝</Button>
            </>
          )}
          {r.approval_status === 'rejected' && (
            <Button size="small" type="primary" style={{ background: '#52c41a', borderColor: '#52c41a' }}
              onClick={() => handleConfirm(r.id)}>重新确认</Button>
          )}
          <Dropdown trigger={['click']} menu={{
            items: transitions(r.status).map(t => ({ key: t.status, label: t.label, danger: t.danger })),
            onClick: ({ key }) => {
              const next = transitions(r.status).find(t => t.status === key);
              if (next) setStatusConfirm({ vehicle: r, status: next.status, label: next.label });
            },
          }}>
            <Button size="small">状态 <DownOutlined /></Button>
          </Dropdown>
          <Popconfirm title="确认解绑该车辆？" onConfirm={() => handleUnbind(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>解绑</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 未选择企业（无企业数据）时的空态
  if (currentEid === null && enterprises.length === 0 && !loading) {
    return (
      <PageWrapper loading={false} hasData={false} transition="slide-up">
        <Empty description="暂无企业，请先在「车队企业」中创建企业后再管理车辆" style={{ padding: 48 }} />
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      loading={loading && vehicles.length === 0}
      skeletonType="table"
      hasData={vehicles.length > 0}
      empty={{ type: 'default', title: '暂无车辆', description: '点击「绑定新车」添加企业车辆', actionText: '绑定新车', onAction: () => setCreateOpen(true) }}
      transition="slide-up"
    >
      <div className="page-container">
        {/* 统计卡片 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="车辆总数" value={stats.total} prefix={<CarOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="在役" value={stats.active} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="维修中" value={stats.maintenance} valueStyle={{ color: '#f5a623' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="待确认" value={stats.pending} valueStyle={{ color: '#faad14' }} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Input placeholder="搜索车牌/VIN/司机" prefix={<SearchOutlined />} value={search}
              onChange={e => setSearch(e.target.value)} style={{ width: 220 }} allowClear />
            <Select placeholder="状态筛选" value={statusFilter} onChange={v => setStatusFilter(v)}
              allowClear style={{ width: 120 }}
              options={[...STATUS_OPTIONS]} />
            <Select placeholder="确认状态" value={approvalFilter} onChange={v => setApprovalFilter(v)}
              allowClear style={{ width: 120 }}
              options={APPROVAL_OPTIONS} />
            <Button icon={<ReloadOutlined />} onClick={loadVehicles}>刷新</Button>
            {selectedRowKeys.length > 0 && (
              <Button type="primary" onClick={handleBatchConfirm}>
                批量确认 ({selectedRowKeys.length})
              </Button>
            )}
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>绑定新车</Button>
          </Space>
        }>
          <Table
            columns={columns}
            dataSource={filtered}
            rowKey="id"
            loading={loading}
            scroll={{ x: 1140 }}
            rowSelection={{
              selectedRowKeys,
              onChange: setSelectedRowKeys,
            }}
            onRow={(r: Vehicle) => ({ onClick: () => openDetail(r), style: { cursor: 'pointer' } })}
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          />
        </Card>

        {/* 绑定新车 Modal */}
        <VehicleCreate
          open={createOpen}
          enterpriseId={currentEid}
          drivers={drivers}
          onCancel={() => setCreateOpen(false)}
          onSuccess={() => { setCreateOpen(false); loadVehicles(); }}
        />

        {/* 详情 Drawer */}
        <VehicleDetail
          open={detailOpen}
          vehicle={detailVehicle}
          onClose={() => { setDetailOpen(false); setDetailVehicle(null); }}
          onStatusChange={handleStatusChange}
        />

        {/* 列表状态变更的受控确认浮层 */}
        <Popconfirm
          title={statusConfirm ? `确认${statusConfirm.label}？` : ''}
          open={!!statusConfirm}
          onConfirm={() => {
            if (statusConfirm) handleStatusChange(statusConfirm.vehicle, statusConfirm.status);
            setStatusConfirm(null);
          }}
          onCancel={() => setStatusConfirm(null)}
          okText="确认"
          cancelText="取消"
        >
          <span />
        </Popconfirm>
      </div>
    </PageWrapper>
  );
};

export default FleetVehiclesPage;
