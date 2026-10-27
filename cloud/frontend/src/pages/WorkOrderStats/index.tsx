/**
 * 工单统计页 - 按状态/工程师/级别/站点统计 + 图表展示
 */
import React, { useEffect, useState, useMemo } from 'react';
import {
  Card, Table, Spin, Row, Col, Select, DatePicker, Statistic,
  Tag, Segmented,
} from 'antd';
import {
  FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined,
  UserOutlined, ThunderboltOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

const { RangePicker } = DatePicker;

interface WorkOrderRecord {
  id: string;
  fault_desc: string;
  type: string;
  level: string;
  status: string;
  station_id: number | null;
  device_id: number | null;
  assignee_id: number | null;
  assignee_name?: string;
  creator_id: number;
  create_time: string;
  accept_time: string | null;
  finish_time: string | null;
  solution: string | null;
  fault_reason?: string;
  parts_replaced?: string;
}

interface StatsData {
  by_status: Record<string, number>;
  by_engineer: Record<string, number>;
  by_level: Record<string, number>;
  by_station: Record<string, number>;
  total: number;
  completed: number;
  avg_duration_hours?: number;
}

type GroupBy = 'status' | 'engineer' | 'level' | 'station';

const statusLabels: Record<string, string> = {
  pending: '待派单', accepted: '已接单', processing: '处理中',
  pending_verify: '待验收', completed: '已完成', cancelled: '已取消', verified: '已验收'
};
const levelLabels: Record<string, string> = {
  urgent: '紧急', high: '高', warning: '一般', low: '低', medium: '中'
};

const WorkOrderStats: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<WorkOrderRecord[]>([]);
  const [groupBy, setGroupBy] = useState<GroupBy>('status');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      // 卡 604c1e16: /work-orders page_size 契约 le=100, 手拼 500 必 422 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<WorkOrderRecord>(
        (params) => api.get('/work-orders', { params }),
        { start_date: dateRange?.[0], end_date: dateRange?.[1] },
      );
      setOrders(items);
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
    }
  };

  // 统计数据
  const stats: StatsData = useMemo(() => {
    const by_status: Record<string, number> = {};
    const by_engineer: Record<string, number> = {};
    const by_level: Record<string, number> = {};
    const by_station: Record<string, number> = {};
    let total = 0;
    let completed = 0;

    orders.forEach(o => {
      const st = o.status || 'unknown';
      const lv = o.level || 'unknown';
      const eng = o.assignee_name || o.assignee_id ? `工程师#${o.assignee_id}` : '未分配';
      const sta = o.station_id ? `站点#${o.station_id}` : '未关联';

      by_status[st] = (by_status[st] || 0) + 1;
      by_engineer[eng] = (by_engineer[eng] || 0) + 1;
      by_level[lv] = (by_level[lv] || 0) + 1;
      by_station[sta] = (by_station[sta] || 0) + 1;
      total++;
      if (st === 'completed' || st === 'verified') completed++;
    });
    return { by_status, by_engineer, by_level, by_station, total, completed };
  }, [orders]);

  // 排序后的分组统计数据
  const groupedData = useMemo(() => {
    const map = stats[`by_${groupBy}` as keyof StatsData] as Record<string, number>;
    return Object.entries(map)
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count);
  }, [stats, groupBy]);

  // 饼图配置
  const pieOption = useMemo(() => {
    const data = groupedData.map(item => ({
      name: groupBy === 'status' ? statusLabels[item.key] || item.key
        : groupBy === 'level' ? levelLabels[item.key] || item.key
        : item.key,
      value: item.count,
    }));
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', right: 10, top: 'center', type: 'scroll' },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        label: { show: true, formatter: '{b}: {c}' },
        emphasis: { label: { fontSize: 16, fontWeight: 'bold' } },
        data,
      }],
    };
  }, [groupedData, groupBy]);

  // 柱状图配置
  const barOption = useMemo(() => {
    const names = groupedData.map(d => groupBy === 'status' ? statusLabels[d.key] || d.key
      : groupBy === 'level' ? levelLabels[d.key] || d.key : d.key);
    const values = groupedData.map(d => d.count);
    return {
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: names,
        axisLabel: { rotate: names.length > 5 ? 30 : 0, fontSize: 11 },
      },
      yAxis: { type: 'value', name: '工单数' },
      series: [{
        type: 'bar',
        data: values,
        itemStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#667eea' },
              { offset: 1, color: '#764ba2' },
            ],
          },
        },
        barMaxWidth: 50,
      }],
      grid: { left: 50, right: 20, top: 20, bottom: names.length > 5 ? 80 : 40 },
    };
  }, [groupedData, groupBy]);

  // 表格数据
  const tableData = useMemo(() => groupedData.map((item, index) => ({
    key: item.key,
    rank: index + 1,
    name: groupBy === 'status' ? statusLabels[item.key] || item.key
      : groupBy === 'level' ? levelLabels[item.key] || item.key : item.key,
    count: item.count,
    percent: stats.total > 0 ? ((item.count / stats.total) * 100).toFixed(1) + '%' : '0%',
  })), [groupedData, groupBy, stats.total]);

  const groupByOptions = [
    { label: '按状态', value: 'status' as GroupBy },
    { label: '按工程师', value: 'engineer' as GroupBy },
    { label: '按级别', value: 'level' as GroupBy },
    { label: '按站点', value: 'station' as GroupBy },
  ];

  const tableColumns = [
    { title: '排名', dataIndex: 'rank', key: 'rank', width: 60 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '工单数', dataIndex: 'count', key: 'count', width: 100, sorter: (a: any, b: any) => a.count - b.count,
    },
    {
      title: '占比', dataIndex: 'percent', key: 'percent', width: 100,
    },
    {
      title: '占比条形图', dataIndex: 'count', key: 'bar',
      render: (count: number) => {
        const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
        return (
          <div style={{ width: '100%', background: '#f0f0f0', borderRadius: 4, height: 16, overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.max(pct, 1)}%`,
                height: '100%',
                background: 'linear-gradient(90deg, #667eea, #764ba2)',
                borderRadius: 4,
                transition: 'width 0.5s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                paddingRight: 4,
                color: '#fff',
                fontSize: 10,
                minWidth: pct > 0 ? 0 : 'auto',
              }}
            >
              {pct > 10 ? `${pct.toFixed(0)}%` : ''}
            </div>
          </div>
        );
      },
    },
  ];

  const handleDateRangeChange = (dates: any, dateStrings: [string, string]) => {
    if (dates && dateStrings[0] && dateStrings[1]) {
      setDateRange(dateStrings);
    } else {
      setDateRange(null);
    }
  };

  const handleDateSearch = () => {
    fetchOrders();
  };

  return (
    <div className="page-container">
      {/* 顶部统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="工单总数"
              value={stats.total}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#667eea' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="已完成"
              value={stats.completed}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#34a853' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="待派单"
              value={stats.by_status.pending || 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#f5a623' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="紧急工单"
              value={stats.by_level.urgent || 0}
              prefix={<ExclamationCircleOutlined />}
              valueStyle={{ color: (stats.by_level.urgent || 0) > 0 ? '#ea4335' : '#34a853' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 分组选择和日期范围 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <span style={{ marginRight: 8, color: '#666' }}>统计维度:</span>
            <Segmented
              value={groupBy}
              onChange={v => setGroupBy(v as GroupBy)}
              options={groupByOptions}
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right' }}>
            <RangePicker
              onChange={handleDateRangeChange}
              placeholder={['开始日期', '结束日期']}
              style={{ width: 260 }}
            />
            <span
              style={{ marginLeft: 8, color: '#667eea', cursor: 'pointer', fontSize: 13 }}
              onClick={handleDateSearch}
            >
              查询
            </span>
          </Col>
        </Row>
      </Card>

      {loading ? (
        <div style={{ padding: 80, textAlign: 'center' }}><Spin size="large" /></div>
      ) : (
        <>
          {/* 图表区域 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={12}>
              <Card title="分布饼图">
                <ReactECharts option={pieOption} style={{ height: 350 }} />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="数量柱状图">
                <ReactECharts option={barOption} style={{ height: 350 }} />
              </Card>
            </Col>
          </Row>

          {/* 统计表格 */}
          <Card title="统计明细">
            <Table
              columns={tableColumns}
              dataSource={tableData}
              pagination={false}
              size="small"
              rowKey="key"
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0}>合计</Table.Summary.Cell>
                  <Table.Summary.Cell index={1}>{tableData.length} 项</Table.Summary.Cell>
                  <Table.Summary.Cell index={2}>
                    <b>{stats.total}</b>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={3}>100%</Table.Summary.Cell>
                  <Table.Summary.Cell index={4} />
                </Table.Summary.Row>
              )}
            />
          </Card>
        </>
      )}
    </div>
  );
};

export default WorkOrderStats;
