/**
 * 充电费（费率模板版）— 定价管理子页（2026-10-09 丁哥: 模板+绑定站点/设备+下发/校验）
 *
 * 模板 = 自定义时段(电价+服务费, 合计=充电费) + 绑定(设备>站点>平台默认)。
 * 下发: 按绑定设备推 0x16 计费模板; 校验: 桩端上行证据比对 → 已更新/未更新。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Button, Space, Input, InputNumber, TimePicker, Select, Tag, Popconfirm,
  message, Typography, Modal, Form, Row, Col, Spin, DatePicker,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SaveOutlined, CloudUploadOutlined, SafetyOutlined, DeleteOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import { stationAPI } from '../../../api';
import { deviceAPI, fetchAllPages } from '../../../api';

const { Text } = Typography;

interface PeriodRow {
  key: string;
  name: string;
  start: string;
  end: string;
  period_type: string;
  start_date?: string | null;  // 尖峰生效起始(YYYY-MM-DD)
  end_date?: string | null;    // 尖峰生效截止
  price: number;
  serviceFee: number;
}

interface Tpl {
  id: number;
  name: string;
  kind: string;
  periods: any[];
  station_id?: number | null;
  device_id?: number | null;
  is_default: boolean;
  occupancy_fee?: number | null;
  reservation_fee?: number | null;
}

const PERIOD_OPTS = [
  { value: 'sharp', label: '尖峰', color: '#cf1322' },
  { value: 'peak', label: '高峰', color: '#fa541c' },
  { value: 'flat', label: '平段', color: '#1677ff' },
  { value: 'valley', label: '低谷', color: '#389e0d' },
  { value: 'deep_valley', label: '深谷', color: '#08979c' },
];

const ChargingFeePricing: React.FC = () => {
  const [templates, setTemplates] = useState<Tpl[]>([]);
  const [current, setCurrent] = useState<Tpl | null>(null);
  const [rows, setRows] = useState<PeriodRow[]>([]);
  const [stations, setStations] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dispatching, setDispatching] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [dispatchResult, setDispatchResult] = useState<any>(null);

  const loadTemplates = useCallback(async (preferId?: number) => {
    setLoading(true);
    try {
      const res = await api.get('/operate/pricing-templates/list', { params: { kind: 'charging' } });
      const d = (res.data as any)?.data || res.data;
      const items: Tpl[] = d?.items || [];
      setTemplates(items);
      if (items.length) {
        const tpl = items.find((t) => t.id === preferId) || items[0];
        setCurrent(tpl);
        setRows((tpl.periods || []).map((p: any, i: number) => ({
          key: `t${tpl.id}-p${i}`, name: p.name || '',
          start: (p.start || '00:00').slice(0, 5), end: (p.end || '23:59').slice(0, 5),
          period_type: p.period_type || 'flat',
          start_date: p.start_date || null, end_date: p.end_date || null,
          price: Number(p.price) || 0, serviceFee: Number(p.serviceFee) || 0,
        })));
      } else {
        setCurrent(null);
        setRows([]);
      }
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
    // 卡 971f853e: page_size 契约 le=100, 手拼 100/200 会 422 或静默截断 → fetchAllPages 循环拉全量
    fetchAllPages<any>((params) => stationAPI.list(params))
      .then((items) => setStations(items))
      .catch(() => message.error('站点列表加载失败'));
    fetchAllPages<any>((params) => deviceAPI.list(params))
      .then((items) => setDevices(items))
      .catch(() => message.error('设备列表加载失败'));
  }, [loadTemplates]);

  const selectTemplate = (id: number) => {
    const tpl = templates.find((t) => t.id === id);
    if (tpl) {
      setCurrent(tpl);
      setRows((tpl.periods || []).map((p: any, i: number) => ({
        key: `t${tpl.id}-p${i}`, name: p.name || '',
        start: (p.start || '00:00').slice(0, 5), end: (p.end || '23:59').slice(0, 5),
        period_type: p.period_type || 'flat',
        start_date: p.start_date || null, end_date: p.end_date || null,
        price: Number(p.price) || 0, serviceFee: Number(p.serviceFee) || 0,
      })));
    }
  };

  const updateRow = (key: string, patch: Partial<PeriodRow>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const createTemplate = async () => {
    try {
      const res = await api.post('/operate/pricing-templates', {
        name: `新费率模板 ${new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)}`,
        kind: 'charging', periods: [], is_default: false,
      });
      message.success('模板已创建');
      loadTemplates((res.data as any)?.data?.id);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败');
    }
  };

  const removeTemplate = async () => {
    if (!current) return;
    try {
      await api.delete(`/operate/pricing-templates/${current.id}`);
      message.success('模板已删除');
      loadTemplates();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败');
    }
  };

  const save = async () => {
    if (!current) return;
    if (!current.station_id && !current.device_id) {
      message.warning('必须绑定站点或设备 —— 每个站点必须定义价格才能运营');
      return;
    }
    setSaving(true);
    try {
      await api.put(`/operate/pricing-templates/${current.id}`, {
        name: current.name, kind: 'charging',
        periods: rows.map((r) => ({
          name: r.name, start: r.start, end: r.end, period_type: r.period_type,
          start_date: r.period_type === 'sharp' ? (r.start_date || null) : null,
          end_date: r.period_type === 'sharp' ? (r.end_date || null) : null,
          price: Number(r.price) || 0, serviceFee: Number(r.serviceFee) || 0,
        })),
        station_id: current.station_id || null,
        device_id: current.device_id || null,
        is_default: false,
      });
      message.success('费率模板已保存');
      loadTemplates();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const dispatchTpl = async () => {
    if (!current) return;
    setDispatching(true);
    try {
      await save();
      const res = await api.post(`/operate/pricing-templates/${current.id}/dispatch`);
      const d = (res.data as any)?.data || res.data;
      if (!d?.results?.length) {
        message.warning('模板未绑定设备/站点，无下发对象——请先绑定设备或站点');
      } else {
        setDispatchResult(d);
        message.success(res.data?.message || '下发完成');
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '下发失败');
    } finally {
      setDispatching(false);
    }
  };

  const verifyTpl = async () => {
    if (!current) return;
    setVerifying(true);
    try {
      const res = await api.post(`/operate/pricing-templates/${current.id}/verify`);
      const d = (res.data as any)?.data || res.data;
      setVerifyResult(d);
      if (d?.updated) message.success('桩端费率已更新');
      else message.warning(res.data?.message || '桩端费率未更新');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '校验失败');
    } finally {
      setVerifying(false);
    }
  };

  const columns: any[] = [
    { title: '时段名称', dataIndex: 'name', width: 120,
      render: (_: any, r: PeriodRow) => (
        <Input size="small" value={r.name} placeholder="如: 早高峰"
          onChange={(e) => updateRow(r.key, { name: e.target.value })} />
      ) },
    { title: '起止时间', dataIndex: 'start', width: 200,
      render: (_: any, r: PeriodRow) => (
        <Space size={4}>
          <TimePicker size="small" format="HH:mm" allowClear={false}
            value={dayjs(r.start, 'HH:mm')}
            onChange={(t) => updateRow(r.key, { start: t ? t.format('HH:mm') : '00:00' })} />
          <Text type="secondary">~</Text>
          <TimePicker size="small" format="HH:mm" allowClear={false}
            value={dayjs(r.end, 'HH:mm')}
            onChange={(t) => updateRow(r.key, { end: t ? t.format('HH:mm') : '23:59' })} />
        </Space>
      ) },
    { title: '类型', dataIndex: 'period_type', width: 95,
      render: (_: any, r: PeriodRow) => (
        <Select size="small" value={r.period_type} style={{ width: 80 }}
          onChange={(v) => updateRow(r.key, { period_type: v })}>
          {PERIOD_OPTS.map((p) => <Select.Option key={p.value} value={p.value}>{p.label}</Select.Option>)}
        </Select>
      ) },
    { title: '时段电价(元/度)', dataIndex: 'price', width: 130,
      render: (_: any, r: PeriodRow) => (
        <InputNumber size="small" min={0} max={10} step={0.01} style={{ width: 105 }}
          value={r.price} onChange={(v) => updateRow(r.key, { price: v || 0 })} />
      ) },
    { title: '时段服务费(元/度)', dataIndex: 'serviceFee', width: 145,
      render: (_: any, r: PeriodRow) => (
        <InputNumber size="small" min={0} max={10} step={0.01} style={{ width: 105 }}
          value={r.serviceFee} onChange={(v) => updateRow(r.key, { serviceFee: v || 0 })} />
      ) },
    { title: '生效期限(尖峰)', key: 'daterange', width: 250,
      render: (_: any, r: PeriodRow) => r.period_type === 'sharp' ? (
        <DatePicker.RangePicker size="small" format="YYYY-MM-DD"
          value={[r.start_date ? dayjs(r.start_date) : null, r.end_date ? dayjs(r.end_date) : null] as any}
          onChange={(vs: any) => updateRow(r.key, {
            start_date: vs?.[0] ? vs[0].format('YYYY-MM-DD') : null,
            end_date: vs?.[1] ? vs[1].format('YYYY-MM-DD') : null,
          })} />
      ) : <Text type="secondary">—</Text> },
    { title: '充电费(合计)', dataIndex: 'total', width: 120,
      render: (_: any, r: PeriodRow) => {
        const total = (Number(r.price) || 0) + (Number(r.serviceFee) || 0);
        const color = PERIOD_OPTS.find((p) => p.value === r.period_type)?.color;
        return <Tag color={color}>{total.toFixed(2)} 元/度</Tag>;
      } },
    { title: '', key: 'del', width: 50,
      render: (_: any, r: PeriodRow) => (
        <Button size="small" type="text" danger icon={<DeleteOutlined />}
          onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} />
      ) },
  ];

  return (
    <Spin spinning={loading}>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select style={{ width: 220 }} value={current?.id}
          placeholder="选择费率模板" onChange={selectTemplate}>
          {templates.map((t) => (
            <Select.Option key={t.id} value={t.id}>
              {t.name}
              {t.station_id ? ` · 站点#${t.station_id}` : ''}{t.device_id ? ` · 设备#${t.device_id}` : ''}
            </Select.Option>
          ))}
        </Select>
        <Button size="small" icon={<PlusOutlined />} onClick={createTemplate}>新建模板</Button>
        {current && (
          <Popconfirm title={`删除模板「${current.name}」?`} onConfirm={removeTemplate}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除模板</Button>
          </Popconfirm>
        )}
        <Button icon={<ReloadOutlined />} onClick={() => loadTemplates()}>刷新</Button>
      </Space>

      {current && (
        <>
          <Row gutter={12} style={{ marginBottom: 12 }} wrap>
            <Col><Input size="small" style={{ width: 180 }} addonBefore="模板名"
              value={current.name} onChange={(e) => setCurrent({ ...current, name: e.target.value })} /></Col>
            <Col>
              <Select size="small" style={{ width: 200 }} allowClear placeholder="绑定站点(整站)"
                value={current.station_id || undefined}
                onChange={(v) => setCurrent({ ...current, station_id: v || null, device_id: null })}>
                {stations.map((s: any) => <Select.Option key={s.id} value={s.id}>{s.name}</Select.Option>)}
              </Select>
            </Col>
            <Col>
              <Select size="small" style={{ width: 220 }} allowClear showSearch optionFilterProp="children"
                placeholder="绑定设备(优先于站点)"
                value={current.device_id || undefined}
                onChange={(v) => setCurrent({ ...current, device_id: v || null })}>
                {devices.map((d: any) => (
                  <Select.Option key={d.id} value={d.id}>{d.name}({d.sn})</Select.Option>
                ))}
              </Select>
            </Col>
          </Row>
          <Space style={{ marginBottom: 12 }} wrap>
            <Button type="primary" ghost icon={<CloudUploadOutlined />} loading={dispatching} onClick={dispatchTpl}>
              下发
            </Button>
            <Button icon={<SafetyOutlined />} loading={verifying} onClick={verifyTpl}>校验</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存</Button>
            <Button icon={<PlusOutlined />} onClick={() => setRows((rs) => [...rs,
              { key: `new-${Date.now()}`, name: '', start: '00:00', end: '23:59',
                period_type: 'flat', price: 0, serviceFee: 0 }])}>添加时段</Button>
            <Text type="secondary">充电费 = 时段电价 + 时段服务费；绑定优先级: 设备 &gt; 站点 &gt; 平台默认</Text>
          </Space>
          <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} />
        </>
      )}

      {/* 下发明细 */}
      <Modal title="费率下发明细" open={!!dispatchResult} footer={null}
             onCancel={() => setDispatchResult(null)} width={520}>
        {(dispatchResult?.results || []).map((r: any, i: number) => (
          <div key={i} style={{ marginBottom: 6 }}>
            <Tag color={String(r.result).includes('已下发') ? 'green' : 'orange'}>{r.result}</Tag>
            <Text>{r.name} ({r.device})</Text>
          </div>
        ))}
      </Modal>

      {/* 校验结果 */}
      <Modal title={(
          <Space>
            <SafetyOutlined />
            <span>费率校验</span>
            {verifyResult && (
              <Tag color={verifyResult.updated ? 'success' : 'error'}>
                {verifyResult.updated ? '✓ 桩端费率已更新' : '✗ 桩端费率未更新'}
              </Tag>
            )}
          </Space>
        )} open={!!verifyResult} onCancel={() => setVerifyResult(null)}
        footer={<Button type="primary" onClick={() => setVerifyResult(null)}>知道了</Button>} width={640}>
        <Table size="small" rowKey="item" dataSource={verifyResult?.items || []} pagination={false}
          columns={[
            { title: '校验项', dataIndex: 'item', width: 200 },
            { title: '期望', dataIndex: 'expected', width: 180 },
            { title: '实际', dataIndex: 'actual', width: 180 },
            { title: '结果', dataIndex: 'ok', width: 90, render: (v: any) =>
              v === true ? <Tag color="success">✓ 通过</Tag> :
              v === false ? <Tag color="error">✗ 异常</Tag> :
              <Tag color="default">待确认</Tag> },
          ]} />
      </Modal>
    </Spin>
  );
};

export default ChargingFeePricing;
