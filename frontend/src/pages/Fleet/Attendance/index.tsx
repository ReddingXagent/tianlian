/**
 * 车队 - 司机考勤/工时页面
 *
 * 功能：司机+月份选择 / 月度考勤列表 / 汇总卡片(出勤率/工时) / 批量录入(按日期范围生成)
 * API:
 *   GET  /fleet/attendance?driver_id=&month=
 *   GET  /fleet/attendance/summary?driver_id=&month=
 *   POST /fleet/attendance/batch   { driver_id, month, records:[...] }
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Select, Space, message,
  Statistic, Row, Col, DatePicker, InputNumber, Input,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, CalendarOutlined, ClockCircleOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface DriverLite { id: number; name: string; phone?: string; }
interface AttendanceRow {
  id: number; driver_id: number; date: string;
  shift_type: string; hours: number; status: string; remark?: string;
}
interface AttendanceSummary {
  total_days: number; total_hours: number;
  normal_days: number; late_days: number; absent_days: number; rest_days: number;
  attendance_rate: number;
}

/* ── 常量 ── */
const SHIFT_TYPES = [
  { value: 'day', label: '白班' },
  { value: 'night', label: '夜班' },
  { value: 'rest', label: '休息' },
];
const STATUSES = [
  { value: 'normal', label: '正常' },
  { value: 'late', label: '迟到' },
  { value: 'absent', label: '缺勤' },
];
const SHIFT_TEXT: Record<string, string> = { day: '白班', night: '夜班', rest: '休息' };
const SHIFT_COLOR: Record<string, string> = { day: 'blue', night: 'purple', rest: 'default' };
const STATUS_TEXT: Record<string, string> = { normal: '正常', late: '迟到', absent: '缺勤' };
const STATUS_COLOR: Record<string, string> = { normal: 'green', late: 'orange', absent: 'red' };

/* ── 组件 ── */
const FleetAttendancePage: React.FC = () => {
  const [drivers, setDrivers] = useState<DriverLite[]>([]);
  const [driverId, setDriverId] = useState<number | null>(null);
  const [month, setMonth] = useState<dayjs.Dayjs>(dayjs());
  const monthStr = month.format('YYYY-MM');

  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchForm] = Form.useForm();

  /* ── 加载 ── */
  const loadDrivers = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/drivers');
      const items: DriverLite[] = Array.isArray(data) ? data : (data as any)?.items || [];
      setDrivers(items);
      if (items.length && driverId === null) setDriverId(items[0].id);
    } catch {
      setDrivers([]);
    }
  }, [driverId]);

  const loadData = useCallback(async () => {
    if (!driverId) { setRows([]); setSummary(null); return; }
    setLoading(true);
    try {
      const [listRes, sumRes] = await Promise.all([
        api.get('/fleet/attendance', { params: { driver_id: driverId, month: monthStr } }),
        api.get('/fleet/attendance/summary', { params: { driver_id: driverId, month: monthStr } }),
      ]);
      setRows(Array.isArray(listRes.data) ? listRes.data : (listRes.data as any)?.items || []);
      setSummary(sumRes.data || null);
    } catch {
      setRows([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [driverId, monthStr]);

  useEffect(() => { loadDrivers(); }, [loadDrivers]);
  useEffect(() => { if (driverId) loadData(); }, [driverId, loadData]);

  /* ── 批量录入 ── */
  const handleBatchSubmit = async () => {
    try {
      const values = await batchForm.validateFields();
      const range: [dayjs.Dayjs, dayjs.Dayjs] = values.range;
      if (!range || !range[0] || !range[1]) {
        message.warning('请选择日期范围');
        return;
      }
      const records: any[] = [];
      let cur = range[0].clone();
      while (cur.isBefore(range[1]) || cur.isSame(range[1], 'day')) {
        records.push({
          date: cur.format('YYYY-MM-DD'),
          shift_type: values.shift_type,
          hours: Number(values.hours) || 0,
          status: values.status,
          remark: values.remark || undefined,
        });
        cur = cur.add(1, 'day');
      }
      await api.post('/fleet/attendance/batch', {
        driver_id: values.driver_id,
        month: values.driver_id === driverId ? monthStr : dayjs(range[0]).format('YYYY-MM'),
        records,
      });
      message.success(`已批量录入 ${records.length} 条考勤`);
      setBatchOpen(false);
      batchForm.resetFields();
      if (values.driver_id === driverId) loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('录入失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openBatch = () => {
    batchForm.resetFields();
    batchForm.setFieldsValue({
      driver_id: driverId ?? undefined,
      shift_type: 'day',
      hours: 8,
      status: 'normal',
    });
    setBatchOpen(true);
  };

  const columns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
    { title: '班次', dataIndex: 'shift_type', key: 'shift_type', width: 90, render: (v: string) => <Tag color={SHIFT_COLOR[v] || 'default'}>{SHIFT_TEXT[v] || v}</Tag> },
    { title: '工时(h)', dataIndex: 'hours', key: 'hours', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '0.0' },
    { title: '出勤状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_TEXT[v] || v}</Tag> },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v: string) => v || '-' },
  ];

  if (driverId === null && drivers.length === 0 && !loading) {
    return (
      <PageWrapper loading={false} hasData={false} transition="slide-up">
        <Card><div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无司机，请先在「司机管理」中添加司机。</div></Card>
      </PageWrapper>
    );
  }

  const rate = summary ? (summary.attendance_rate * 100).toFixed(1) + '%' : '-';
  const avgHours = summary && summary.total_days ? (summary.total_hours / summary.total_days).toFixed(1) : '0.0';

  return (
    <PageWrapper
      loading={loading && rows.length === 0}
      skeletonType="table"
      hasData={rows.length > 0}
      empty={{ type: 'default', title: '本月暂无考勤记录', description: '点击「批量录入」按日期范围生成司机考勤', actionText: '批量录入', onAction: openBatch }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="出勤率" value={rate} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="总工时(h)" value={summary?.total_hours ?? 0} prefix={<ClockCircleOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="日均工时(h)" value={avgHours} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="记录天数" value={summary?.total_days ?? 0} prefix={<CalendarOutlined />} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择司机" value={driverId ?? undefined} onChange={setDriverId}
              style={{ width: 180 }} showSearch optionFilterProp="label"
              options={drivers.map(d => ({ value: d.id, label: `${d.name}${d.phone ? ` (${d.phone})` : ''}` }))} />
            <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openBatch} disabled={!driverId}>批量录入</Button>
          </Space>
        }>
          <Table columns={columns} dataSource={rows} rowKey="id" loading={loading}
            pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          />
        </Card>

        {/* 批量录入 Modal */}
        <Modal title="批量录入考勤" open={batchOpen} onOk={handleBatchSubmit}
          onCancel={() => { setBatchOpen(false); batchForm.resetFields(); }}
          width={520} destroyOnHidden
        >
          <Form form={batchForm} layout="vertical">
            <Form.Item name="driver_id" label="司机" rules={[{ required: true, message: '请选择司机' }]}>
              <Select placeholder="选择司机" showSearch optionFilterProp="label"
                options={drivers.map(d => ({ value: d.id, label: `${d.name}${d.phone ? ` (${d.phone})` : ''}` }))} />
            </Form.Item>
            <Form.Item name="range" label="日期范围" rules={[{ required: true, message: '请选择日期范围' }]}>
              <DatePicker.RangePicker style={{ width: '100%' }} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="shift_type" label="班次" rules={[{ required: true }]}>
                  <Select options={SHIFT_TYPES} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="hours" label="每日工时(h)" rules={[{ required: true, message: '请输入工时' }]}>
                  <InputNumber style={{ width: '100%' }} min={0} max={24} step={0.5} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="status" label="出勤状态" rules={[{ required: true }]}>
                  <Select options={STATUSES} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="remark" label="备注">
              <Input placeholder="可选备注" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetAttendancePage;
