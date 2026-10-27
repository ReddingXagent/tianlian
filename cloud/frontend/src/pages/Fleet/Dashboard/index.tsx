/**
 * 车队 - 概览看板页面
 *
 * 对接 GET /api/v1/fleet/overview?enterprise_id={eid}
 *
 * 5 张统计卡片 + 1 张近期交易列表：
 *   1. 企业基础信息  —— 名称/编码/余额/状态/信用额度
 *   2. 车队规模      —— 车辆总数 + 在役/维修/退役分布(进度条)
 *   3. 充电运营      —— 累计充电量(kWh)/累计消费(元)
 *   4. V2G 收益      —— 累计放电量/收益/响应次数
 *   5. 碳减排        —— 累计减排/节油/车辆数
 *   6. 近期交易列表  —— 最近 5 笔(类型/金额/余额/时间)
 *
 * 字段契约对齐后端 app/api/v1/fleet_overview.py（success_response 包装）：
 *   data.enterprise        = { id, name, code, balance, status }
 *   data.total_vehicles    = number
 *   data.total_charged_kwh = number
 *   data.total_spent       = number
 *   data.recent_transactions[] = { id, type(recharge/consume/refund), amount, balance_after, created_at }
 *
 * 后端未返回的字段(信用额度 / 车辆状态分布 / V2G / 碳减排)统一兜底显示 '--'。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Select, Button, Space, Tag, Table, Progress,
  Empty, Descriptions, Spin, message,
} from 'antd';
import {
  DashboardOutlined, BankOutlined, CarOutlined, ThunderboltOutlined,
  SwapOutlined, ExperimentOutlined, ReloadOutlined, UnorderedListOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface EnterpriseLite {
  id: number;
  name: string;
  code?: string;
  status?: string;
}

interface OverviewEnterprise {
  id: number;
  name?: string;
  code?: string;
  balance?: number;
  credit_limit?: number;
  status?: string;
}

interface Transaction {
  id: number;
  type?: string;
  amount?: number;
  balance_after?: number;
  order_id?: string;
  remark?: string;
  created_at?: string;
}

interface OverviewData {
  enterprise?: OverviewEnterprise;
  total_vehicles?: number;
  active_vehicles?: number;
  maintenance_vehicles?: number;
  retired_vehicles?: number;
  total_charged_kwh?: number;
  total_spent?: number;
  v2g_discharge_kwh?: number;
  v2g_revenue?: number;
  v2g_response_count?: number;
  carbon_reduction_kg?: number;
  fuel_saved_l?: number;
  carbon_vehicles?: number;
  recent_transactions?: Transaction[];
}

/* ── 常量 ── */
const TAG_COLORS: Record<string, string> = {
  active: 'green', normal: 'green', enabled: 'green',
  inactive: 'red', suspended: 'orange', frozen: 'red', maintenance: 'orange',
};
const STATUS_TEXT: Record<string, string> = {
  active: '启用', normal: '正常', inactive: '停用', suspended: '暂停', frozen: '冻结', maintenance: '维护中',
};

const TX_TYPE: Record<string, { text: string; color: string }> = {
  recharge: { text: '充值', color: 'green' },
  consume: { text: '消费', color: 'orange' },
  refund: { text: '退款', color: 'blue' },
};

/* ── 兜底格式化 ── */
const fmtNum = (v?: number): number | string => (v == null ? '--' : v);
const fmtKwh = (v?: number): string => (v == null ? '--' : `${v.toLocaleString()} kWh`);
const fmtMoney = (v?: number): string => (v == null
  ? '--'
  : `¥ ${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
const fmtTime = (t?: string): string => (t ? t.replace('T', ' ').slice(0, 16) : '--');

/* ── 组件 ── */
const FleetDashboardPage: React.FC = () => {
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [enterpriseId, setEnterpriseId] = useState<number | undefined>();
  const [listLoading, setListLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overview, setOverview] = useState<OverviewData | null>(null);

  /* ── 加载企业列表 ── */
  const loadList = useCallback(async () => {
    setListLoading(true);
    try {
      const { data: body } = await api.get('/enterprises');
      const items: EnterpriseLite[] = body?.data?.items || body?.items || [];
      setEnterprises(items);
      if (items.length) setEnterpriseId(items[0].id);
    } catch {
      setEnterprises([]);
    } finally {
      setListLoading(false);
    }
  }, []);

  /* ── 加载概览 ── */
  const loadOverview = useCallback(async (eid: number) => {
    setOverviewLoading(true);
    try {
      const { data: body } = await api.get('/fleet/overview', { params: { enterprise_id: eid } });
      const d: OverviewData = body?.data || body || {};
      setOverview(d);
    } catch (err: any) {
      message.error('加载车队概览失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setOverviewLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (enterpriseId) loadOverview(enterpriseId); }, [enterpriseId, loadOverview]);

  /* ── 派生 ── */
  const ent = overview?.enterprise;
  const totalV = overview?.total_vehicles ?? 0;
  const activeV = overview?.active_vehicles;
  const inServiceRate = totalV > 0 && activeV != null ? Math.round((activeV / totalV) * 100) : 0;
  const txs = overview?.recent_transactions || [];

  /* ── 近期交易列 ── */
  const txColumns = [
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 90,
      render: (t: string) => {
        const m = TX_TYPE[t || ''] || { text: t || '--', color: 'default' };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '金额', dataIndex: 'amount', key: 'amount', width: 150, align: 'right' as const,
      render: (v?: number) => (v == null ? '--' : (
        <span style={{ color: v >= 0 ? '#34a853' : '#ea4335', fontWeight: 600 }}>{fmtMoney(v)}</span>
      )),
    },
    {
      title: '余额', dataIndex: 'balance_after', key: 'balance_after', width: 150, align: 'right' as const,
      render: (v?: number) => fmtMoney(v),
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (t: string) => fmtTime(t),
    },
  ];

  return (
    <PageWrapper loading={listLoading && !enterpriseId} hasData transition="slide-up">
      <div className="page-container">
        {/* 工具条 */}
        <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              <DashboardOutlined /> 车队概览看板
            </span>
          </Col>
          <Col>
            <Space>
              <Select
                style={{ width: 240 }}
                value={enterpriseId}
                onChange={(v: number) => setEnterpriseId(v)}
                placeholder="选择企业"
                showSearch
                optionFilterProp="label"
                options={enterprises.map(e => ({ value: e.id, label: e.name }))}
              />
              <Button icon={<ReloadOutlined />} onClick={() => (enterpriseId ? loadOverview(enterpriseId) : loadList())}>
                刷新
              </Button>
            </Space>
          </Col>
        </Row>

        <Spin spinning={overviewLoading}>
          <Row gutter={[16, 16]}>
            {/* 1. 企业基础信息 */}
            <Col xs={24} lg={8}>
              <Card title={<span><BankOutlined /> 企业基础信息</span>} size="small">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="名称">{ent?.name || '--'}</Descriptions.Item>
                  <Descriptions.Item label="编码">
                    {ent?.code ? <Tag color="blue">{ent.code}</Tag> : '--'}
                  </Descriptions.Item>
                  <Descriptions.Item label="余额">{fmtMoney(ent?.balance)}</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={TAG_COLORS[ent?.status || ''] || 'default'}>
                      {STATUS_TEXT[ent?.status || ''] || ent?.status || '--'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="信用额度">{fmtMoney(ent?.credit_limit)}</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>

            {/* 2. 车队规模 */}
            <Col xs={24} lg={8}>
              <Card title={<span><CarOutlined /> 车队规模</span>} size="small">
                <Statistic title="车辆总数" value={fmtNum(overview?.total_vehicles)} />
                <div style={{ marginTop: 12 }}>
                  <Progress
                    percent={inServiceRate}
                    size="small"
                    status="active"
                    format={() => `在役率 ${activeV != null ? inServiceRate : '--'}%`}
                  />
                </div>
                <Row gutter={8} style={{ marginTop: 12 }}>
                  <Col span={8}><Statistic title="在役" value={fmtNum(overview?.active_vehicles)} valueStyle={{ fontSize: 16 }} /></Col>
                  <Col span={8}><Statistic title="维修" value={fmtNum(overview?.maintenance_vehicles)} valueStyle={{ fontSize: 16 }} /></Col>
                  <Col span={8}><Statistic title="退役" value={fmtNum(overview?.retired_vehicles)} valueStyle={{ fontSize: 16 }} /></Col>
                </Row>
              </Card>
            </Col>

            {/* 3. 充电运营 */}
            <Col xs={24} lg={8}>
              <Card title={<span><ThunderboltOutlined /> 充电运营</span>} size="small">
                <Statistic title="累计充电量" value={fmtKwh(overview?.total_charged_kwh)} />
                <Statistic title="累计消费" value={fmtMoney(overview?.total_spent)} valueStyle={{ marginTop: 16 }} />
              </Card>
            </Col>

            {/* 4. V2G 收益 */}
            <Col xs={24} lg={8}>
              <Card title={<span><SwapOutlined /> V2G 收益</span>} size="small">
                <Statistic title="累计放电量" value={fmtKwh(overview?.v2g_discharge_kwh)} />
                <Row gutter={8} style={{ marginTop: 16 }}>
                  <Col span={12}><Statistic title="累计收益" value={fmtMoney(overview?.v2g_revenue)} /></Col>
                  <Col span={12}><Statistic title="响应次数" value={fmtNum(overview?.v2g_response_count)} /></Col>
                </Row>
              </Card>
            </Col>

            {/* 5. 碳减排 */}
            <Col xs={24} lg={8}>
              <Card title={<span><ExperimentOutlined /> 碳减排</span>} size="small">
                <Row gutter={8}>
                  <Col span={12}><Statistic title="累计减排(kg)" value={fmtNum(overview?.carbon_reduction_kg)} /></Col>
                  <Col span={12}><Statistic title="累计节油(L)" value={fmtNum(overview?.fuel_saved_l)} /></Col>
                </Row>
                <Statistic title="参与车辆" value={fmtNum(overview?.carbon_vehicles)} valueStyle={{ marginTop: 16 }} />
              </Card>
            </Col>

            {/* 6. 近期交易列表 */}
            <Col xs={24}>
              <Card title={<span><UnorderedListOutlined /> 近期交易</span>} size="small">
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={txs}
                  columns={txColumns}
                  pagination={false}
                  locale={{ emptyText: <Empty description="暂无交易记录" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                />
              </Card>
            </Col>
          </Row>
        </Spin>
      </div>
    </PageWrapper>
  );
};

export default FleetDashboardPage;
