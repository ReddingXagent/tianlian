/**
 * 虚拟电厂(VPP)调度优化页面
 *
 * 功能:
 * 1. VPP聚合容量仪表盘
 * 2. 站点状态卡片
 * 3. 调度执行面板
 * 4. 调度历史记录
 * 5. 实时电价趋势
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Select, Space, Spin, Typography, Table, Tag,
  Button, InputNumber, Progress, message, Divider, Tooltip, Badge, Radio,
  Descriptions, Alert, Modal, Form, Input,
} from 'antd';
import {
  ThunderboltOutlined, DashboardOutlined, ApiOutlined,
  RocketOutlined, HistoryOutlined, DollarOutlined,
  ReloadOutlined, PlusOutlined, DeleteOutlined,
  PoweroffOutlined, SunOutlined,
  CarOutlined, NodeIndexOutlined,
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, CanvasRenderer]);

import api from '../../api';

const { Text, Title: AntTitle } = Typography;

const API_BASE = '/vpp'; // axios baseURL 已含 /api/v1，此处只给段前缀，防双前缀

// 调度模式映射
const MODE_MAP: Record<string, { label: string; color: string }> = {
  auto: { label: '自动', color: '#ff5a36' },
  economic: { label: '经济调度', color: '#34a853' },
  peak_shaving: { label: '削峰填谷', color: '#f5a623' },
  demand_response: { label: '需求响应', color: '#ea4335' },
  multi_station: { label: '多站点协同', color: '#722ed1' },
};

// ─── 通用 api helper ───
async function vppFetch<T = any>(path: string, opts?: { method?: string; body?: any }): Promise<T> {
  const method = (opts?.method || 'GET').toLowerCase();
  const config: any = { method, url: `${API_BASE}${path}` };
  if (opts?.body) { config.data = opts.body; }
  const res = await api(config);
  const json = res.data;
  if (json.code !== undefined && json.code !== 200) throw new Error(json.message || '请求失败');
  return json.data ?? json;
}

// ─── 站点卡片 ───
const StationCard: React.FC<{ station: any; onDelete: (id: string) => void }> = ({ station, onDelete }) => {
  const socPercent = Math.round((station.current_battery_soc || 0) * 100);
  const socColor = socPercent > 60 ? '#34a853' : socPercent > 30 ? '#f5a623' : '#ea4335';

  return (
    <Card
      size="small"
      title={
        <Space>
          <Badge status={station.online ? 'success' : 'default'} />
          <Text strong>{station.station_name}</Text>
          {!station.online && <Tag color="default">离线</Tag>}
        </Space>
      }
      extra={
        <Tooltip title="注销站点">
          <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => onDelete(station.station_id)} />
        </Tooltip>
      }
      style={{ marginBottom: 12 }}
    >
      <Row gutter={[8, 8]}>
        <Col span={12}>
          <Statistic
            title={<><SunOutlined /> 光伏</>}
            value={station.current_pv_output_kw}
            suffix={`/ ${station.total_pv_kw}kW`}
            valueStyle={{ fontSize: 14 }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={<><ThunderboltOutlined /> 储能SOC</>}
            value={socPercent}
            suffix="%"
            valueStyle={{ fontSize: 14, color: socColor }}
          />
          <Progress percent={socPercent} showInfo={false} strokeColor={socColor} size="small" />
        </Col>
        <Col span={12}>
          <Statistic title="负荷" value={station.current_load_kw} suffix="kW" valueStyle={{ fontSize: 14 }} />
        </Col>
        <Col span={12}>
          <Statistic title="可调度" value={station.available_dispatch_kw} suffix="kW" valueStyle={{ fontSize: 14 }} />
        </Col>
      </Row>
    </Card>
  );
};

// ─── 站点注册弹窗 ───
const RegisterStationModal: React.FC<{ open: boolean; onClose: () => void; onOk: () => void }> = ({ open, onClose, onOk }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await vppFetch('/stations', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      message.success('站点注册成功');
      form.resetFields();
      onOk();
      onClose();
    } catch (e: any) {
      if (e.errorFields) return;
      message.error(e.message || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="注册新站点" open={open} onOk={handleSubmit} onCancel={onClose} confirmLoading={loading}>
      <Form form={form} layout="vertical" initialValues={{ total_ev_chargers: 0, current_battery_soc: 0.5 }}>
        <Form.Item name="station_id" label="站点ID" rules={[{ required: true }]}>
          <Input placeholder="ST-006" />
        </Form.Item>
        <Form.Item name="station_name" label="站点名称" rules={[{ required: true }]}>
          <Input placeholder="站点名称" />
        </Form.Item>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="total_pv_kw" label="光伏装机(kW)">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="total_battery_kwh" label="储能容量(kWh)">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="current_load_kw" label="当前负荷(kW)">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="current_pv_output_kw" label="光伏出力(kW)">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
};

// ─── 主页面 ───
const VPPPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [capacity, setCapacity] = useState<any>(null);
  const [stations, setStations] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [priceInfo, setPriceInfo] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);

  // 调度面板状态
  const [dispatchMode, setDispatchMode] = useState<string>('auto');
  const [peakThreshold, setPeakThreshold] = useState<number>(500);
  const [drTargetKw, setDrTargetKw] = useState<number>(200);
  const [drDuration, setDrDuration] = useState<number>(30);
  const [drReward, setDrReward] = useState<number>(0.5);
  const [dispatching, setDispatching] = useState(false);

  // 站点注册弹窗
  const [registerOpen, setRegisterOpen] = useState(false);

  // 各区块加载失败态：失败渲染错误提示+重试，绝不回退假数据
  const SECTION_LABELS = {
    capacity: '聚合容量', stations: '站点状态', history: '调度历史', price: '电价信息',
  } as const;
  type SectionKey = keyof typeof SECTION_LABELS;
  const [errors, setErrors] = useState<Partial<Record<SectionKey, string>>>({});
  const setError = (key: SectionKey, text: string | null) =>
    setErrors(prev => {
      const next = { ...prev };
      if (text) next[key] = text; else delete next[key];
      return next;
    });
  const errorText = (e: any) => e?.response?.data?.message || e?.response?.data?.detail || e?.message || '加载失败';

  // ─── 数据加载 ───
  const loadCapacity = useCallback(async () => {
    try {
      const data = await vppFetch('/capacity');
      setCapacity(data);
      setError('capacity', null);
    } catch (e: any) {
      setCapacity(null);
      setError('capacity', errorText(e));
      message.error('VPP容量加载失败：' + errorText(e));
    }
  }, []);

  const loadStations = useCallback(async () => {
    try {
      const data = await vppFetch('/stations');
      setStations(data);
      setError('stations', null);
    } catch (e: any) {
      setStations([]);
      setError('stations', errorText(e));
      message.error('站点状态加载失败：' + errorText(e));
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const data = await vppFetch('/dispatch/history?limit=20');
      setHistory(data);
      setError('history', null);
    } catch (e: any) {
      setHistory([]);
      setError('history', errorText(e));
      message.error('调度历史加载失败：' + errorText(e));
    }
  }, []);

  const loadPrice = useCallback(async () => {
    try {
      const data = await vppFetch('/price');
      setPriceInfo(data);
      setError('price', null);
    } catch (e: any) {
      setPriceInfo(null);
      setError('price', errorText(e));
      message.error('电价信息加载失败：' + errorText(e));
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadCapacity(), loadStations(), loadHistory(), loadPrice()]);
    setLoading(false);
  }, [loadCapacity, loadStations, loadHistory, loadPrice]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // ─── 调度执行 ───
  const handleDispatch = async () => {
    setDispatching(true);
    try {
      const body: any = { mode: dispatchMode };
      if (dispatchMode === 'peak_shaving') {
        body.peak_threshold_kw = peakThreshold;
      }
      if (dispatchMode === 'demand_response') {
        body.grid_signal = {
          signal_type: 'demand_response',
          target_power_kw: drTargetKw,
          duration_min: drDuration,
          reward_per_kwh: drReward,
          urgency: 0.7,
        };
      }
      const result = await vppFetch('/dispatch', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setLastResult(result);
      message.success(`调度完成！计划ID: ${result.plan_id}`);
      loadHistory();
      loadCapacity();
    } catch (e: any) {
      message.error(e.message || '调度失败');
    } finally {
      setDispatching(false);
    }
  };

  // ─── 站点注销 ───
  const handleDeleteStation = async (stationId: string) => {
    try {
      await vppFetch(`/stations/${stationId}`, { method: 'DELETE' });
      message.success('站点已注销');
      loadStations();
      loadCapacity();
    } catch (e: any) {
      message.error(e.message || '注销失败');
    }
  };

  // ─── 重新加载模拟数据 ───
  const handleReloadSim = async () => {
    try {
      await vppFetch('/simulate?count=5', { method: 'POST' });
      message.success('模拟数据已重新加载');
      loadAll();
    } catch (e: any) {
      message.error(e.message || '重新加载失败');
    }
  };

  // ─── 电价趋势图 ───
  const getPriceChartOption = () => {
    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const prices = hours.map((_, i) => {
      const h = i + 0.5;
      if (h >= 10 && h < 12) return 1.2;
      if ((h >= 8 && h < 10) || (h >= 18 && h < 21)) return 0.9;
      if (h >= 23 || h < 6) return 0.3;
      return 0.6;
    });
    const currentHour = priceInfo?.hour ?? new Date().getHours() + new Date().getMinutes() / 60;

    return {
      tooltip: { trigger: 'axis' as const },
      grid: { top: 30, right: 20, bottom: 30, left: 50 },
      xAxis: { type: 'category' as const, data: hours },
      yAxis: { type: 'value' as const, name: '元/kWh', min: 0, max: 1.5 },
      series: [{
        type: 'line',
        data: prices,
        smooth: true,
        areaStyle: { opacity: 0.15 },
        lineStyle: { width: 2, color: '#ff5a36' },
        itemStyle: { color: '#ff5a36' },
        markLine: {
          symbol: 'none' as const,
          data: [{ xAxis: Math.floor(currentHour) }],
          lineStyle: { color: '#ea4335', width: 2, type: 'solid' as const },
          label: { formatter: '当前', color: '#ea4335' },
        },
      }],
    };
  };

  // ─── 调度历史列定义 ───
  const historyColumns = [
    { title: '计划ID', dataIndex: 'plan_id', key: 'plan_id', width: 200, ellipsis: true },
    {
      title: '模式', dataIndex: 'mode', key: 'mode', width: 110,
      render: (v: string) => {
        const m = MODE_MAP[v];
        return m ? <Tag color={m.color}>{m.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    { title: '触发原因', dataIndex: 'trigger', key: 'trigger', ellipsis: true },
    { title: '调度功率(kW)', dataIndex: 'total_dispatch_kw', key: 'dispatch_kw', width: 120, render: (v: number) => v?.toFixed(1) },
    { title: '收益(元)', dataIndex: 'estimated_revenue', key: 'revenue', width: 100, render: (v: number) => v?.toFixed(2) },
    { title: '成本(元)', dataIndex: 'estimated_cost', key: 'cost', width: 100, render: (v: number) => v?.toFixed(2) },
    { title: '净利润(元)', dataIndex: 'net_profit', key: 'profit', width: 110, render: (v: number) => <Text type={v >= 0 ? 'success' : 'danger'}>{v?.toFixed(2)}</Text> },
    { title: '时间', dataIndex: 'created_at', key: 'time', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
  ];

  return (
    <div style={{ padding: 16, background: '#faf5f4', minHeight: '100vh' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <AntTitle level={4} style={{ margin: 0 }}>
          <ThunderboltOutlined /> 虚拟电厂(VPP)调度优化
        </AntTitle>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>刷新</Button>
          <Button icon={<ApiOutlined />} onClick={handleReloadSim}>重载模拟数据</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterOpen(true)}>注册站点</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* ── 数据加载失败提示（含重试）── */}
        {Object.keys(errors).length > 0 && (
          <Alert type="error" showIcon style={{ marginBottom: 16 }}
            message="部分数据加载失败"
            description={Object.entries(errors).map(([k, v]) => `${SECTION_LABELS[k as SectionKey]}：${v}`).join('；')}
            action={<Button size="small" icon={<ReloadOutlined />} onClick={loadAll}>重试</Button>}
          />
        )}

        {/* ── a) 总览仪表盘 ── */}
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="在线站点" value={capacity?.online_stations ?? '-'} suffix={`/ ${capacity?.total_stations ?? '-'}`}
                prefix={<NodeIndexOutlined />} valueStyle={{ fontSize: 16 }} />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="光伏装机" value={capacity?.total_pv_kw ?? '-'} suffix="kW"
                prefix={<SunOutlined />} valueStyle={{ fontSize: 16, color: '#f5a623' }} />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="储能容量" value={capacity?.total_battery_kwh ?? '-'} suffix="kWh"
                prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 16, color: '#34a853' }} />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="可调度功率" value={capacity?.available_dispatch_kw ?? '-'} suffix="kW"
                prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 16, color: '#ff5a36' }} />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="平均SOC" value={capacity ? Math.round((capacity.avg_battery_soc ?? 0) * 100) : '-'} suffix="%"
                prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 16, color: '#34a853' }} />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic title="当前电价"
                value={priceInfo?.current_price ?? '-'}
                suffix={`元/kWh`}
                prefix={<DollarOutlined />}
                valueStyle={{ fontSize: 16, color: priceInfo?.period === '低谷' ? '#34a853' : priceInfo?.period === '尖峰' ? '#ea4335' : '#f5a623' }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>{priceInfo?.period ?? '-'}</Text>
            </Card>
          </Col>
        </Row>

        <Row gutter={[12, 12]}>
          {/* ── 左栏: 站点 + 调度 ── */}
          <Col xs={24} lg={14}>
            {/* ── b) 站点状态卡片 ── */}
            <Card title={<><DashboardOutlined /> 站点状态</>} size="small" style={{ marginBottom: 12 }}>
              {stations.length === 0 ? (
                errors.stations ? (
                  <Alert type="error" showIcon message="站点状态加载失败" description={errors.stations}
                    action={<Button size="small" icon={<ReloadOutlined />} onClick={loadStations}>重试</Button>} />
                ) : (
                  <Alert message="暂无站点，请注册或重载模拟数据" type="info" showIcon />
                )
              ) : (
                <Row gutter={[12, 0]}>
                  {stations.map((s) => (
                    <Col xs={24} sm={12} key={s.station_id}>
                      <StationCard station={s} onDelete={handleDeleteStation} />
                    </Col>
                  ))}
                </Row>
              )}
            </Card>

            {/* ── c) 调度执行面板 ── */}
            <Card title={<><RocketOutlined /> 调度执行</>} size="small" style={{ marginBottom: 12 }}>
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div>
                  <Text strong>调度模式：</Text>
                  <Radio.Group value={dispatchMode} onChange={(e) => setDispatchMode(e.target.value)} optionType="button" buttonStyle="solid">
                    {Object.entries(MODE_MAP).map(([k, v]) => (
                      <Radio.Button key={k} value={k}>{v.label}</Radio.Button>
                    ))}
                  </Radio.Group>
                </div>

                {dispatchMode === 'peak_shaving' && (
                  <div>
                    <Text>削峰阈值(kW)：</Text>
                    <InputNumber min={100} max={5000} value={peakThreshold} onChange={(v) => setPeakThreshold(v ?? 500)} style={{ width: 160 }} />
                  </div>
                )}

                {dispatchMode === 'demand_response' && (
                  <Row gutter={12}>
                    <Col span={8}>
                      <Text>目标功率(kW)：</Text>
                      <InputNumber min={10} max={5000} value={drTargetKw} onChange={(v) => setDrTargetKw(v ?? 200)} style={{ width: '100%' }} />
                    </Col>
                    <Col span={8}>
                      <Text>持续时间(min)：</Text>
                      <InputNumber min={5} max={240} value={drDuration} onChange={(v) => setDrDuration(v ?? 30)} style={{ width: '100%' }} />
                    </Col>
                    <Col span={8}>
                      <Text>奖励(元/kWh)：</Text>
                      <InputNumber min={0} max={5} step={0.1} value={drReward} onChange={(v) => setDrReward(v ?? 0.5)} style={{ width: '100%' }} />
                    </Col>
                  </Row>
                )}

                <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleDispatch} loading={dispatching} block size="large">
                  执行调度
                </Button>

                {/* 调度结果 */}
                {lastResult && (
                  <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
                    <Descriptions title={`调度结果: ${lastResult.plan_id}`} size="small" column={2}>
                      <Descriptions.Item label="调度功率">{lastResult.total_dispatch_kw} kW</Descriptions.Item>
                      <Descriptions.Item label="参与站点">{lastResult.stations_involved?.length ?? 0} 个</Descriptions.Item>
                      <Descriptions.Item label="预估收益"><Text type="success">{lastResult.estimated_revenue} 元</Text></Descriptions.Item>
                      <Descriptions.Item label="预估成本"><Text type="danger">{lastResult.estimated_cost} 元</Text></Descriptions.Item>
                      <Descriptions.Item label="净利润"><Text strong type={lastResult.net_profit >= 0 ? 'success' : 'danger'}>{lastResult.net_profit} 元</Text></Descriptions.Item>
                      <Descriptions.Item label="指令数">{lastResult.commands?.length ?? 0}</Descriptions.Item>
                    </Descriptions>
                  </Card>
                )}
              </Space>
            </Card>
          </Col>

          {/* ── 右栏: 电价 + 历史 ── */}
          <Col xs={24} lg={10}>
            {/* ── e) 电价趋势 ── */}
            <Card title={<><DollarOutlined /> 24小时电价趋势</>} size="small" style={{ marginBottom: 12 }}>
              {errors.price && (
                <Alert type="error" showIcon style={{ marginBottom: 12 }}
                  message="电价信息加载失败" description={errors.price}
                  action={<Button size="small" icon={<ReloadOutlined />} onClick={loadPrice}>重试</Button>} />
              )}
              <ReactEChartsCore
                echarts={echarts}
                option={getPriceChartOption()}
                style={{ height: 220 }}
                notMerge
              />
              {priceInfo && (
                <div style={{ marginTop: 8, textAlign: 'center' }}>
                  <Space>
                    <Tag color="#ea4335">尖峰 {priceInfo.price_schedule?.peak}元</Tag>
                    <Tag color="#f5a623">高峰 {priceInfo.price_schedule?.high}元</Tag>
                    <Tag color="#ff5a36">平段 {priceInfo.price_schedule?.flat}元</Tag>
                    <Tag color="#34a853">低谷 {priceInfo.price_schedule?.valley}元</Tag>
                  </Space>
                </div>
              )}
            </Card>

            {/* ── d) 调度历史 ── */}
            <Card title={<><HistoryOutlined /> 调度历史</>} size="small">
              {errors.history && (
                <Alert type="error" showIcon style={{ marginBottom: 12 }}
                  message="调度历史加载失败" description={errors.history}
                  action={<Button size="small" icon={<ReloadOutlined />} onClick={loadHistory}>重试</Button>} />
              )}
              <Table
                dataSource={history}
                columns={historyColumns}
                rowKey="plan_id"
                size="small"
                pagination={{ pageSize: 5 }}
                scroll={{ x: 900 }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>

      {/* 站点注册弹窗 */}
      <RegisterStationModal open={registerOpen} onClose={() => setRegisterOpen(false)} onOk={loadAll} />
    </div>
  );
};

export default VPPPage;
