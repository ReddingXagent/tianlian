/**
 * V2G 电价（费率模板版）— 定价管理子页（2026-10-09 丁哥: V2G 放电价也要模板化）
 *
 * 模板 = 自定义时段(购电/放电) + 电价 + 绑定(设备>站点>平台默认)。
 * 下发: 仅购电(buy)时段经 0x16 推送(V2G桩充电成本); 放电(sell)价为平台策略, 协议无下发通道。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Button, Space, Input, InputNumber, TimePicker, Select, Tag, Popconfirm,
  message, Typography, Spin, Modal, Row, Col,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SaveOutlined, CloudUploadOutlined, SafetyOutlined, DeleteOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import { stationAPI, deviceAPI, fetchAllPages } from '../../../api';

const { Text } = Typography;

interface PeriodRow {
  key: string;
  name: string;
  start: string;
  end: string;
  kind: 'buy' | 'sell';
  price: number;
}

interface Tpl {
  id: number;
  name: string;
  kind: string;
  periods: any[];
  station_id?: number | null;
  device_id?: number | null;
  is_default: boolean;
}

const V2GPricing: React.FC = () => {
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

  const applyTpl = (tpl: Tpl) => {
    setCurrent(tpl);
    setRows((tpl.periods || []).map((p: any, i: number) => ({
      key: `t${tpl.id}-p${i}`, name: p.name || '',
      start: (p.start || '00:00').slice(0, 5), end: (p.end || '23:59').slice(0, 5),
      kind: p.kind === 'sell' ? 'sell' : 'buy',
      price: Number(p.price) || 0,
    })));
  };

  const loadTemplates = useCallback(async (preferId?: number) => {
    setLoading(true);
    try {
      const res = await api.get('/operate/pricing-templates/list', { params: { kind: 'v2g' } });
      const d = (res.data as any)?.data || res.data;
      const items: Tpl[] = d?.items || [];
      setTemplates(items);
      if (items.length) applyTpl(items.find((t) => t.id === preferId) || items[0]);
      else { setCurrent(null); setRows([]); }
    } catch { setTemplates([]); }
    finally { setLoading(false); }
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

  const updateRow = (key: string, patch: Partial<PeriodRow>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const createTemplate = async () => {
    try {
      const res = await api.post('/operate/pricing-templates', {
        name: `V2G电价模板 ${new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)}`,
        kind: 'v2g', periods: [], is_default: false,
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
        name: current.name, kind: 'v2g',
        periods: rows.map((r) => ({
          name: r.name, start: r.start, end: r.end,
          kind: r.kind, price: Number(r.price) || 0,
        })),
        station_id: current.station_id || null,
        device_id: current.device_id || null,
        is_default: false,
      });
      message.success('V2G 电价模板已保存');
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
    { title: '时段名称', dataIndex: 'name', width: 130,
      render: (_: any, r: PeriodRow) => (
        <Input size="small" value={r.name} placeholder="如: 晚高峰"
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
    { title: '类型', dataIndex: 'kind', width: 100,
      render: (_: any, r: PeriodRow) => (
        <Select size="small" value={r.kind} style={{ width: 85 }}
          onChange={(v) => updateRow(r.key, { kind: v })}>
          <Select.Option value="sell">放电</Select.Option>
          <Select.Option value="buy">购电</Select.Option>
        </Select>
      ) },
    { title: '电价(元/度)', dataIndex: 'price', width: 130,
      render: (_: any, r: PeriodRow) => (
        <InputNumber size="small" min={0} max={10} step={0.01} style={{ width: 105 }}
          value={r.price} onChange={(v) => updateRow(r.key, { price: v || 0 })} />
      ) },
    { title: '说明', key: 'note',
      render: (_: any, r: PeriodRow) => (
        r.kind === 'sell'
          ? <Text type="warning">V2G 放电卖电收益(平台策略)</Text>
          : <Text type="secondary">充电购电成本(可下发桩端)</Text>
      ) },
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
          placeholder="选择 V2G 电价模板"
          onChange={(id) => { const t = templates.find((x) => x.id === id); if (t) applyTpl(t); }}>
          {templates.map((t) => (
            <Select.Option key={t.id} value={t.id}>
              {t.name}
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
                placeholder="绑定V2G设备(优先)"
                value={current.device_id || undefined}
                onChange={(v) => setCurrent({ ...current, device_id: v || null })}>
                {devices.filter((d: any) => d.type === 'v2g_charger').map((d: any) => (
                  <Select.Option key={d.id} value={d.id}>{d.name}({d.sn})</Select.Option>
                ))}
              </Select>
            </Col>
          </Row>
          <Space style={{ marginBottom: 12 }} wrap>
            <Button type="primary" ghost icon={<CloudUploadOutlined />} loading={dispatching} onClick={dispatchTpl}>
              下发(购电时段)
            </Button>
            <Button icon={<SafetyOutlined />} loading={verifying} onClick={verifyTpl}>校验</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存</Button>
            <Button icon={<PlusOutlined />} onClick={() => setRows((rs) => [...rs,
              { key: `new-${Date.now()}`, name: '', start: '00:00', end: '23:59', kind: 'sell', price: 0 }])}>
              添加时段
            </Button>
            <Text type="secondary">购电时段=充电成本(可下发0x16)；放电时段=V2G卖电收益(平台结算策略，协议无下发通道)</Text>
          </Space>
          <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} />
        </>
      )}

      <Modal title="下发明细" open={!!dispatchResult} footer={null}
             onCancel={() => setDispatchResult(null)} width={520}>
        {(dispatchResult?.results || []).map((r: any, i: number) => (
          <div key={i} style={{ marginBottom: 6 }}>
            <Tag color={String(r.result).includes('已下发') ? 'green' : 'orange'}>{r.result}</Tag>
            <Text>{r.name} ({r.device})</Text>
          </div>
        ))}
      </Modal>

      <Modal title={(
          <Space>
            <SafetyOutlined /><span>V2G 费率校验</span>
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

export default V2GPricing;
