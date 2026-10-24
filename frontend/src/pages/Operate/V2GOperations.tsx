/**
 * V2G 运营（车网互动）— 2026-10-09 丁哥需求
 *
 * 调研结论: V2G 运营核心四块
 *  1) 概览看板: 双向桩规模/在线率/充放电状态
 *  2) 峰谷套利策略: 低谷充/高峰放电时段与价差
 *  3) 车辆资源池: 参与车辆(VIN/车牌/司机)
 *  4) 放电订单: 卖电交易与结算(随交易模型扩展接入, 当前空态)
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Table, Tag, Statistic, Row, Col, Spin, Typography, Empty, Space, Input, InputNumber, Button, Modal, Form, message,
} from 'antd';
import {
  ThunderboltOutlined, ArrowDownOutlined, ArrowUpOutlined, CarOutlined,
  RiseOutlined, ToolOutlined, SettingOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { useNavigate } from 'react-router-dom';

const { Text } = Typography;


const V2GOperations: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  // V2G 峰谷电价(可设置, 2026-10-09 丁哥需求)
  const [pricing, setPricing] = useState<any>({ periods: [] });
  const [savingPrice, setSavingPrice] = useState(false);
    
  const fetchPricing = async () => {
    try {
      const res = await api.get('/operate/v2g/pricing');
      const d = (res.data as any)?.data || res.data;
      if (d) setPricing(d);
    } catch { /* 默认值兜底 */ }
  };

      const [vehicles, setVehicles] = useState<any[]>([]);
  const [vTotal, setVTotal] = useState(0);
  const [vPage, setVPage] = useState(1);
  const [keyword, setKeyword] = useState('');

  const fetchOverview = async () => {
    try {
      const res = await api.get('/operate/v2g/overview');
      setOverview((res.data as any)?.data || res.data);
    } catch { /* 静默 */ }
  };

  const fetchVehicles = async (p = vPage, kw = keyword) => {
    try {
      const res = await api.get('/operate/v2g/vehicles', {
        params: { page: p, page_size: 8, keyword: kw || undefined },
      });
      const d = (res.data as any)?.data || res.data;
      setVehicles(d?.items || []);
      setVTotal(d?.total || 0);
    } catch { /* 静默 */ }
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      await Promise.all([fetchOverview(), fetchVehicles(1, ''), fetchPricing()]);
      setLoading(false);
    })();
  }, []);

  const piles = overview?.piles || { total: 0, online: 0, charging: 0, fault: 0, online_rate: 0 };
  const vehiclesStat = overview?.vehicles || { total: 0, active: 0 };

  return (
    <Spin spinning={loading}>
      {/* 概览看板 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="V2G双向桩" value={piles.total} prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="在线" value={piles.online} suffix={<Text type="secondary">({piles.online_rate}%)</Text>} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="充电中" value={piles.charging} prefix={<ArrowDownOutlined />} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="故障" value={piles.fault} prefix={<ToolOutlined />} valueStyle={{ color: piles.fault ? '#faad14' : undefined }} /></Card>
        </Col>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="车辆资源池" value={vehiclesStat.total} prefix={<CarOutlined />} suffix={<Text type="secondary">(活跃{vehiclesStat.active})</Text>} /></Card>
        </Col>
        <Col xs={12} md={4}>
          <Card size="small"><Statistic title="本月放电收益" value={0} prefix={<RiseOutlined />} suffix="元" valueStyle={{ color: '#722ed1' }} /></Card>
        </Col>
      </Row>

      {/* 峰谷套利策略 */}
      <Card size="small" title={<Space><ThunderboltOutlined /><span>峰谷套利策略</span><Tag color="purple">V2G</Tag></Space>}
            style={{ marginBottom: 16 }}
            extra={(
        <Space>
          <Text type="secondary">{overview?.strategy_hint || '低谷充电 · 高峰放电'}</Text>
          <Button size="small" icon={<SettingOutlined />} onClick={() => navigate('/operate/pricing')}>
            设置放电价
          </Button>
        </Space>
      )}>
        <Table
          size="small"
          rowKey={(_r: any, i?: number) => `pp-${i}`}
          pagination={false}
          dataSource={pricing?.periods || []}
          columns={[
            { title: '时段', key: 'period', width: 190, render: (_: any, p: any) => (
              <span>{p.name} {p.start}~{p.end}</span>
            ) },
            { title: '动作', dataIndex: 'kind', width: 100, render: (v: string) => (
              <Tag color={v === 'sell' ? 'volcano' : 'blue'}>{v === 'sell' ? '放电' : '充电'}</Tag>
            ) },
            { title: '电价(元/度)', dataIndex: 'price', width: 120,
              render: (v: number) => `${Number(v ?? 0).toFixed(2)}` },
            { title: '说明', key: 'note', render: (_: any, p: any) => (
              p.kind === 'sell'
                ? <span style={{ color: '#d4380d' }}>卖电给电网, V2G 收益</span>
                : <span style={{ opacity: 0.65 }}>购电蓄能</span>
            ) },
          ]}
        />
      </Card>

      {/* 车辆资源池 */}
      <Card size="small" title={<Space><CarOutlined /><span>V2G车辆资源池</span></Space>}
            extra={
              <Input.Search
                size="small" style={{ width: 220 }} placeholder="车牌/VIN/司机"
                allowClear
                onSearch={(v) => { setKeyword(v); setVPage(1); fetchVehicles(1, v); }}
              />
            }
            style={{ marginBottom: 16 }}>
        <Table
          size="small"
          rowKey="id"
          dataSource={vehicles}
          pagination={{
            current: vPage, pageSize: 8, total: vTotal, size: 'small',
            onChange: (p) => { setVPage(p); fetchVehicles(p); },
          }}
          columns={[
            { title: '车牌号', dataIndex: 'plate_number', width: 110 },
            { title: 'VIN码', dataIndex: 'vin', width: 200, ellipsis: true },
            { title: '司机', dataIndex: 'driver_name', width: 100 },
            { title: '电话', dataIndex: 'driver_phone', width: 130 },
            { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => (
              <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '活跃' : v}</Tag>
            ) },
          ]}
        />
      </Card>

      {/* 放电订单 */}
      <Card size="small" title={<Space><ArrowUpOutlined /><span>放电订单</span></Space>}>
        <Empty
          description={
            <span>
              暂无放电订单<br />
              <Text type="secondary">V2G 桩放电交易产生后在此展示（卖电量/电价/收益/结算状态）</Text>
            </span>
          }
        />
      </Card>
          </Spin>
  );
};

export default V2GOperations;
