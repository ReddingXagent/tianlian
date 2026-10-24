/**
 * 车队 - 车辆详情 Drawer
 *
 * 基础信息(Descriptions) + 多标签(充电历史 / V2G收益 / 碳减排 / 费用汇总) + 状态变更
 * 各 Tab 数据为前端 Mock（后端车辆维度聚合接口尚未实现）。
 */
import React from 'react';
import { Drawer, Descriptions, Tag, Tabs, Table, Button, Space, Popconfirm, Empty } from 'antd';
import type { Vehicle } from './index';

interface VehicleDetailProps {
  open: boolean;
  vehicle: Vehicle | null;
  onClose: () => void;
  onStatusChange: (vehicle: Vehicle, status: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'green', maintenance: 'orange', retired: 'red', inactive: 'default',
};
const STATUS_TEXT: Record<string, string> = {
  active: '在役', maintenance: '维修', retired: '退役', inactive: '停用',
};

/* ── 各 Tab Mock 数据 ── */
const chargeHistory = [
  { id: 1, station: '郑州东站超充站', kwh: 45.2, amount: 58.76, time: '2026-07-18 14:20' },
  { id: 2, station: '广州天河充电站', kwh: 38.0, amount: 49.40, time: '2026-07-15 09:05' },
];
const v2gRevenue = [
  { id: 1, discharge_kwh: 12.5, revenue: 18.75, grid_event: '削峰', time: '2026-07-19 18:30' },
  { id: 2, discharge_kwh: 8.0, revenue: 12.00, grid_event: '填谷', time: '2026-07-12 03:10' },
];
const carbonReduction = [
  { id: 1, month: '2026-07', kwh: 83.2, reduction_kg: 22.5 },
  { id: 2, month: '2026-06', kwh: 76.5, reduction_kg: 20.7 },
];
const costSummary = [
  { id: 1, category: '充电费', amount: 108.16 },
  { id: 2, category: '维保费', amount: 320.00 },
  { id: 3, category: '保险费', amount: 650.00 },
];

/* ── 状态变更可选项（按当前状态推导） ── */
const transitionOptions = (status?: string): { status: string; label: string; danger?: boolean }[] => {
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

const VehicleDetail: React.FC<VehicleDetailProps> = ({ open, vehicle, onClose, onStatusChange }) => {
  const fmtDate = (v?: string) => (v ? v.split('T')[0] : '-');

  const tabItems = [
    {
      key: 'charge',
      label: '充电历史',
      children: (
        <Table dataSource={chargeHistory} rowKey="id" size="small" pagination={{ pageSize: 5 }}
          columns={[
            { title: '充电站', dataIndex: 'station', key: 'station' },
            { title: '电量(kWh)', dataIndex: 'kwh', key: 'kwh', align: 'right' as const },
            { title: '金额(¥)', dataIndex: 'amount', key: 'amount', align: 'right' as const },
            { title: '时间', dataIndex: 'time', key: 'time' },
          ]}
        />
      ),
    },
    {
      key: 'v2g',
      label: 'V2G收益',
      children: (
        <Table dataSource={v2gRevenue} rowKey="id" size="small" pagination={{ pageSize: 5 }}
          columns={[
            { title: '放电(kWh)', dataIndex: 'discharge_kwh', key: 'discharge_kwh', align: 'right' as const },
            { title: '收益(¥)', dataIndex: 'revenue', key: 'revenue', align: 'right' as const },
            { title: '电网事件', dataIndex: 'grid_event', key: 'grid_event' },
            { title: '时间', dataIndex: 'time', key: 'time' },
          ]}
        />
      ),
    },
    {
      key: 'carbon',
      label: '碳减排',
      children: (
        <Table dataSource={carbonReduction} rowKey="id" size="small" pagination={{ pageSize: 5 }}
          columns={[
            { title: '月份', dataIndex: 'month', key: 'month' },
            { title: '充电量(kWh)', dataIndex: 'kwh', key: 'kwh', align: 'right' as const },
            { title: '减排(kg)', dataIndex: 'reduction_kg', key: 'reduction_kg', align: 'right' as const },
          ]}
        />
      ),
    },
    {
      key: 'cost',
      label: '费用汇总',
      children: (
        <Table dataSource={costSummary} rowKey="id" size="small" pagination={{ pageSize: 5 }}
          columns={[
            { title: '费用类别', dataIndex: 'category', key: 'category' },
            { title: '金额(¥)', dataIndex: 'amount', key: 'amount', align: 'right' as const },
          ]}
        />
      ),
    },
  ];

  return (
    <Drawer
      title={vehicle ? `车辆详情 - ${vehicle.plate_number}` : '车辆详情'}
      open={open}
      width={620}
      onClose={onClose}
      destroyOnHidden
    >
      {vehicle ? (
        <>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="车牌号">
              <Tag color="blue" style={{ fontSize: 13 }}>{vehicle.plate_number}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={STATUS_COLORS[vehicle.status] || 'default'}>
                {STATUS_TEXT[vehicle.status] || vehicle.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="VIN码" span={2}>
              <code style={{ fontSize: 12 }}>{vehicle.vin || '-'}</code>
            </Descriptions.Item>
            <Descriptions.Item label="品牌车型">
              {[vehicle.brand, vehicle.model].filter(Boolean).join(' ') || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="绑定司机">
              {vehicle.driver_name || '-'}{vehicle.driver_phone ? ` (${vehicle.driver_phone})` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="绑定时间">{fmtDate(vehicle.created_at)}</Descriptions.Item>
            <Descriptions.Item label="最近更新">{fmtDate(vehicle.updated_at)}</Descriptions.Item>
          </Descriptions>

          {/* 状态变更 */}
          <Space style={{ marginTop: 12 }}>
            {transitionOptions(vehicle.status).map(opt => (
              <Popconfirm
                key={opt.status}
                title={`确认${opt.label}？`}
                onConfirm={() => onStatusChange(vehicle, opt.status)}
              >
                <Button danger={opt.danger}>{opt.label}</Button>
              </Popconfirm>
            ))}
            {transitionOptions(vehicle.status).length === 0 && (
              <span style={{ color: '#999' }}>当前状态无可用变更操作</span>
            )}
          </Space>

          <Tabs items={tabItems} style={{ marginTop: 16 }} />
        </>
      ) : (
        <Empty description="未选择车辆" />
      )}
    </Drawer>
  );
};

export default VehicleDetail;
