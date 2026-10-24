/**
 * 工单列表卡片 — 搜索筛选 + 表格/卡片（响应式）+ 操作列
 *
 * 桌面(≥md)：antd Table + 横排筛选栏
 * 移动(<md)：卡片列表 + 筛选器折叠（搜索框常驻）
 */
import React, { useState } from 'react';
import { Card, Table, Tag, Spin, Button, Select, Input, Space, Popconfirm } from 'antd';
import {
  PlusOutlined, SyncOutlined, CloseCircleOutlined, SearchOutlined,
  EyeOutlined, ThunderboltOutlined, RollbackOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, DownloadOutlined, FilterOutlined,
} from '@ant-design/icons';
import { useIsMobile } from '../../../hooks/useIsMobile';
import { typeLabels, levelColors, statusColors, statusLabels, statusIcons } from '../constants';
import type { WorkOrder } from '../types';

interface WorkOrderListCardProps {
  orders: WorkOrder[];
  loading: boolean;
  searchText: string;
  onSearchChange: (v: string) => void;
  filterStatus: string;
  onFilterStatusChange: (v: string) => void;
  filterLevel: string;
  onFilterLevelChange: (v: string) => void;
  onExport: () => void;
  onCreateOpen: () => void;
  onViewDetail: (o: WorkOrder) => void;
  onAutoDispatch: (o: WorkOrder) => void;
  onStart: (o: WorkOrder) => void;
  onComplete: (o: WorkOrder) => void;
  onVerify: (o: WorkOrder) => void;
  onReject: (o: WorkOrder) => void;
  onTransfer: (o: WorkOrder) => void;
  onUrge: (o: WorkOrder) => void;
}

/** 级别文案（桌面表格与移动卡片共用） */
const levelText = (v: string) =>
  v === 'urgent' ? '紧急' : v === 'high' ? '高' : v === 'warning' ? '一般' : v === 'low' ? '低' : v;

const WorkOrderListCard: React.FC<WorkOrderListCardProps> = ({
  orders, loading,
  searchText, onSearchChange,
  filterStatus, onFilterStatusChange,
  filterLevel, onFilterLevelChange,
  onExport, onCreateOpen,
  onViewDetail, onAutoDispatch, onStart, onComplete, onVerify, onReject, onTransfer, onUrge,
}) => {
  const isMobile = useIsMobile();
  // 移动端筛选器（状态/级别/导出）默认折叠，搜索框常驻
  const [filtersOpen, setFiltersOpen] = useState(false);

  /** 行内操作按钮 —— 桌面表格操作列与移动卡片底部共用，避免移动端功能退化 */
  const renderActionButtons = (record: WorkOrder) => (
    <Space size="small" wrap>
      <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => onViewDetail(record)}>
        详情
      </Button>
      {record.status === 'pending' && (
        <Button size="small" type="link" icon={<SyncOutlined />}
          onClick={() => onAutoDispatch(record)}>
          派单
        </Button>
      )}
      {record.status === 'accepted' && (
        <Button size="small" type="link" icon={<ThunderboltOutlined />}
          onClick={() => onStart(record)}>
          开始
        </Button>
      )}
      {(record.status === 'accepted' || record.status === 'processing') && (
        <Button size="small" type="link" icon={<CheckCircleOutlined />}
          onClick={() => onComplete(record)}>
          完成
        </Button>
      )}
      {record.status === 'pending_verify' && (
        <>
          <Button size="small" type="link" icon={<CheckCircleOutlined />}
            onClick={() => onVerify(record)}>
            验收
          </Button>
          <Button size="small" type="link" danger icon={<CloseCircleOutlined />}
            onClick={() => onReject(record)}>
            驳回
          </Button>
        </>
      )}
      {(record.status === 'pending' || record.status === 'accepted' || record.status === 'processing') && (
        <Button size="small" type="link" icon={<RollbackOutlined />}
          onClick={() => onTransfer(record)}>
          转单
        </Button>
      )}
      {(record.status === 'pending' || record.status === 'accepted' || record.status === 'processing') && (
        <Popconfirm title="确认催单?" onConfirm={() => onUrge(record)}>
          <Button size="small" type="link" icon={<ExclamationCircleOutlined />}>
            催单
          </Button>
        </Popconfirm>
      )}
    </Space>
  );

  const columns = [
    { title: '工单号', dataIndex: 'id', key: 'id', width: 170 },
    {
      title: '故障描述', dataIndex: 'fault_desc', key: 'fault_desc', ellipsis: true,
      render: (v: string) => <span style={{ maxWidth: 300 }}>{v}</span>
    },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 70,
      render: (v: string) => typeLabels[v] || v
    },
    {
      title: '级别', dataIndex: 'level', key: 'level', width: 80,
      render: (v: string) => (
        <Tag color={levelColors[v] || 'default'} icon={v === 'urgent' ? <ExclamationCircleOutlined /> : null}>
          {levelText(v)}
        </Tag>
      )
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => (
        <Tag color={statusColors[v] || 'default'} icon={statusIcons[v] || null}>
          {statusLabels[v] || v}
        </Tag>
      )
    },
    {
      title: '创建时间', dataIndex: 'create_time', key: 'create_time', width: 150,
      render: (v: string) => v ? v.substring(0, 16) : '-'
    },
    {
      title: '操作', key: 'action', width: 220, fixed: 'right' as const,
      render: (_: unknown, record: WorkOrder) => renderActionButtons(record),
    },
  ];

  // ── 筛选器：状态/级别/导出（桌面常驻，移动端折叠） ──
  const filterControls = (
    <>
      <Select
        placeholder="筛选状态"
        allowClear
        style={{ width: 130 }}
        value={filterStatus || undefined}
        onChange={v => onFilterStatusChange(v || '')}
        options={Object.entries(statusLabels).map(([k, v]) => ({ label: v as string, value: k }))}
      />
      <Select
        placeholder="筛选级别"
        allowClear
        style={{ width: 120 }}
        value={filterLevel || undefined}
        onChange={v => onFilterLevelChange(v || '')}
        options={[
          { label: '紧急', value: 'urgent' },
          { label: '高', value: 'high' },
          { label: '一般', value: 'warning' },
          { label: '低', value: 'low' },
        ]}
      />
      <Button
        icon={<DownloadOutlined />}
        onClick={onExport}
        disabled={orders.length === 0}
      >
        导出CSV
      </Button>
    </>
  );

  return (
    <Card
      title="工单列表"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={onCreateOpen}>
          创建工单
        </Button>
      }
    >
      {/* 搜索筛选栏 */}
      {isMobile ? (
        <div style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索工单号/故障描述..."
            allowClear
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => onSearchChange(e.target.value)}
          />
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#999' }}>共 {orders.length} 条</span>
            <Button
              size="small"
              type={filtersOpen ? 'primary' : 'default'}
              icon={<FilterOutlined />}
              onClick={() => setFiltersOpen(o => !o)}
            >
              筛选
            </Button>
          </div>
          {filtersOpen && (
            <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {filterControls}
            </div>
          )}
        </div>
      ) : (
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="搜索工单号/故障描述..."
            allowClear
            style={{ width: 280 }}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => onSearchChange(e.target.value)}
          />
          {filterControls}
          <span style={{ lineHeight: '32px', color: '#999' }}>
            共 {orders.length} 条
          </span>
        </div>
      )}

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>
      ) : isMobile ? (
        // 移动端：卡片列表（每条工单一卡片，信息纵向排布）
        <div>
          {orders.map(record => (
            <Card
              key={record.id}
              size="small"
              data-testid="wo-mobile-card"
              style={{ marginBottom: 8 }}
            >
              {/* 头部：工单号 + 状态 */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <strong>{record.id}</strong>
                <Tag color={statusColors[record.status] || 'default'} icon={statusIcons[record.status] || null}>
                  {statusLabels[record.status] || record.status}
                </Tag>
              </div>
              {/* 故障描述 */}
              <div style={{ marginBottom: 6, color: 'var(--text-primary, #333)' }}>{record.fault_desc}</div>
              {/* 类型 / 级别 / 创建时间 */}
              <Space size={4} wrap style={{ marginBottom: 8 }}>
                <Tag>{typeLabels[record.type] || record.type}</Tag>
                <Tag color={levelColors[record.level] || 'default'} icon={record.level === 'urgent' ? <ExclamationCircleOutlined /> : null}>
                  {levelText(record.level)}
                </Tag>
                <span style={{ color: '#999', fontSize: 12 }}>{record.create_time ? record.create_time.substring(0, 16) : '-'}</span>
              </Space>
              {/* 操作按钮（与桌面表格一致） */}
              {renderActionButtons(record)}
            </Card>
          ))}
        </div>
      ) : (
        <Table
          columns={columns}
          dataSource={orders}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
          size="small"
          scroll={{ x: 1100 }}
        />
      )}
    </Card>
  );
};

export default WorkOrderListCard;
