/**
 * 平台费率模板 — 占桩费/预约费（平台计算，不下发桩端）(2026-10-09 丁哥需求)
 *
 * 与充电费模板分离: 电价+服务费下发桩端(0x16), 占桩/预约费由平台在结算时计算。
 * 每个模板独立绑定: 设备(精确) > 站点(整站) > 平台默认。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Button, Space, Input, InputNumber, Select, Tag, Popconfirm, message, Typography, Spin, Row, Col, Switch,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SaveOutlined, DeleteOutlined, BankOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import { stationAPI, deviceAPI, fetchAllPages } from '../../../api';

const { Text } = Typography;

interface OccRule {
  free_minutes?: number | null; // 免费缓冲(充电完成后驶离豁免)
  unit?: 'minute' | 'hour';     // 计费单位
  price?: number | null;        // 单价(元/分钟 或 元/小时)
  cap?: number | null;          // 单次封顶(元, 空=不封顶)
  busy_double?: boolean;        // 场站满位时费率x2(特斯拉模式)
}

interface Tpl {
  id: number;
  name: string;
  kind: string;
  occupancy_fee?: number | null;   // 旧字段(元/小时, 兼容读回)
  occupancy_rule?: OccRule | null; // 占桩费规则
  reservation_fee?: number | null; // 预约费(元/次)
  station_id?: number | null;
  device_id?: number | null;
  is_default: boolean;
}

const PlatformFeePricing: React.FC = () => {
  const [templates, setTemplates] = useState<Tpl[]>([]);
  const [current, setCurrent] = useState<Tpl | null>(null);
  const [stations, setStations] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadTemplates = useCallback(async (preferId?: number) => {
    setLoading(true);
    try {
      const res = await api.get('/operate/pricing-templates/list', { params: { kind: 'platform' } });
      const d = (res.data as any)?.data || res.data;
      const items: Tpl[] = (d?.items || []).map((t: any) => ({
        ...t,
        occupancy_rule: t.occupancy_rule
          || (t.occupancy_fee != null ? { free_minutes: 10, unit: 'hour', price: Number(t.occupancy_fee), cap: null, busy_double: false } : null),
        reservation_fee: t.reservation_fee ?? null,
      }));
      setTemplates(items);
      setCurrent(items.find((t) => t.id === preferId) || items[0] || null);
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

  const createTemplate = async () => {
    try {
      const res = await api.post('/operate/pricing-templates', {
        name: `平台费率模板 ${new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)}`,
        kind: 'platform', periods: [], is_default: false,
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
        name: current.name, kind: 'platform', periods: [],
        occupancy_fee: null,
        occupancy_rule: (current.occupancy_rule && (current.occupancy_rule.price != null || current.occupancy_rule.free_minutes != null))
          ? current.occupancy_rule : null,
        reservation_fee: current.reservation_fee ?? null,
        station_id: current.station_id || null,
        device_id: current.device_id || null,
        is_default: false,
      });
      message.success('平台费率模板已保存');
      loadTemplates();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select style={{ width: 240 }} value={current?.id}
          placeholder="选择平台费率模板"
          onChange={(id) => setCurrent(templates.find((t) => t.id === id) || null)}>
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
          <Row gutter={[12, 12]} wrap>
            <Col><Input size="small" style={{ width: 200 }} addonBefore="模板名"
              value={current.name} onChange={(e) => setCurrent({ ...current, name: e.target.value })} /></Col>
            <Col>
              <Select size="small" style={{ width: 200 }} allowClear placeholder="绑定站点(整站)"
                value={current.station_id || undefined}
                onChange={(v) => setCurrent({ ...current, station_id: v || null, device_id: null })}>
                {stations.map((s: any) => <Select.Option key={s.id} value={s.id}>{s.name}</Select.Option>)}
              </Select>
            </Col>
            <Col>
              <Select size="small" style={{ width: 240 }} allowClear showSearch optionFilterProp="children"
                placeholder="绑定设备(优先于站点)"
                value={current.device_id || undefined}
                onChange={(v) => setCurrent({ ...current, device_id: v || null })}>
                {devices.map((d: any) => (
                  <Select.Option key={d.id} value={d.id}>{d.name}({d.sn})</Select.Option>
                ))}
              </Select>
            </Col>
          </Row>

          <Row gutter={[24, 12]} style={{ marginTop: 20, maxWidth: 720 }}>
            <Col span={24}>
              <div style={{ padding: 16, border: '1px solid #eee', borderRadius: 8 }}>
                <Space><BankOutlined /><Text strong>占桩费</Text><Tag>平台计算</Tag></Space>
                <Row gutter={[12, 12]} style={{ marginTop: 12 }} align="middle" wrap>
                  <Col>免费缓冲
                    <InputNumber min={0} max={720} step={5} size="small" style={{ width: 90 }}
                      addonAfter="分钟" value={current.occupancy_rule?.free_minutes ?? 10}
                      onChange={(v) => setCurrent({ ...current,
                        occupancy_rule: { ...(current.occupancy_rule || {}), free_minutes: v ?? 10 } as OccRule })} />
                  </Col>
                  <Col>
                    <Select size="small" style={{ width: 95 }} value={current.occupancy_rule?.unit || 'minute'}
                      onChange={(v) => setCurrent({ ...current,
                        occupancy_rule: { ...(current.occupancy_rule || {}), unit: v } as OccRule })}>
                      <Select.Option value="minute">按分钟</Select.Option>
                      <Select.Option value="hour">按小时</Select.Option>
                    </Select>
                  </Col>
                  <Col>
                    <InputNumber min={0} max={999} step={0.1} size="small" style={{ width: 150 }}
                      addonAfter={current.occupancy_rule?.unit === 'hour' ? '元/小时' : '元/分钟'}
                      placeholder="不启用"
                      value={current.occupancy_rule?.price ?? undefined}
                      onChange={(v) => setCurrent({ ...current,
                        occupancy_rule: { ...(current.occupancy_rule || {}), price: (v ?? null) as any } as OccRule })} />
                  </Col>
                  <Col>单次封顶
                    <InputNumber min={0} max={9999} step={10} size="small" style={{ width: 110 }}
                      addonAfter="元" placeholder="不封顶"
                      value={current.occupancy_rule?.cap ?? undefined}
                      onChange={(v) => setCurrent({ ...current,
                        occupancy_rule: { ...(current.occupancy_rule || {}), cap: (v ?? null) as any } as OccRule })} />
                  </Col>
                  <Col>满位加倍
                    <Switch size="small" checked={!!current.occupancy_rule?.busy_double}
                      onChange={(v) => setCurrent({ ...current,
                        occupancy_rule: { ...(current.occupancy_rule || {}), busy_double: v } as OccRule })} />
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>场站无空闲桩时费率×2</Text>
                  </Col>
                </Row>
                <Text type="secondary" style={{ fontSize: 12 }}>充电完成后超过免费缓冲仍未驶离开始计费；不足一个计费单位向上取整；封顶与满位加倍可选</Text>
              </div>
            </Col>
            <Col span={24}>
              <div style={{ padding: 16, border: '1px solid #eee', borderRadius: 8 }}>
                <Space><BankOutlined /><Text strong>预约费</Text><Tag>平台计算</Tag></Space>
                <div style={{ marginTop: 8 }}>
                  <InputNumber min={0} max={999} step={0.1} style={{ width: 180 }} size="small"
                    addonAfter="元/次" placeholder="不启用"
                    value={current.reservation_fee ?? undefined}
                    onChange={(v) => setCurrent({ ...current, reservation_fee: (v ?? null) as any })} />
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>用户预约桩位/时段时收取</Text>
              </div>
            </Col>
          </Row>

          <Space style={{ marginTop: 20 }}>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存</Button>
            <Text type="secondary">占桩费/预约费由平台在结算时计算，不下发充电桩；停车费由停车场系统收取</Text>
          </Space>
        </>
      )}
    </Spin>
  );
};

export default PlatformFeePricing;
