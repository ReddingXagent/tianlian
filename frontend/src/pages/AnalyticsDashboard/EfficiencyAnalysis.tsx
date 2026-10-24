/**
 * 能效分析仪表板
 * 数据源: GET /api/v1/reports/efficiency (效率报表 — 充电效率排名 + 异常低效预警)
 * 卡 980f4d94: 原 POST /analytics/efficiency 后端不存在且有 mock 兜底, 已移除假数据
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Select, Statistic, Table, Tag, Space, Button, message, List, InputNumber
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  ThunderboltOutlined, BulbOutlined, WarningOutlined, ReloadOutlined
} from '@ant-design/icons';
import api, { stationAPI } from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

interface EfficiencyItem {
  device_id: number;
  device_name: string;
  device_code: string;
  device_type: string;
  station_id: number;
  station_name: string;
  charge_efficiency: number;
}

interface EfficiencyReport {
  items: EfficiencyItem[];
  total: number;
  page: number;
  page_size: number;
  alerts: {
    abnormal_low_efficiency: {
      count: number;
      threshold: string;
      items: EfficiencyItem[];
    };
  };
}

const EfficiencyAnalysis: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [selectedStation, setSelectedStation] = useState<number | null>(null);
  const [stations, setStations] = useState<any[]>([]);
  const [minEfficiency, setMinEfficiency] = useState<number>(70);
  const [report, setReport] = useState<EfficiencyReport | null>(null);

  const loadStations = async () => {
    try {
      const { data } = await stationAPI.businessList();
      const items = data?.items || [];
      setStations(items);
      if (items.length > 0) {
        setSelectedStation(items[0].id);
      }
    } catch {
      // 静默处理：站点列表加载失败不影响能效分析交互
    }
  };

  const loadEfficiencyData = useCallback(async (stationId: number | null, threshold: number) => {
    setLoading(true);
    try {
      const extraParams: Record<string, unknown> = { min_efficiency: threshold };
      if (stationId) {
        extraParams.station_id = stationId;
      }
      // 响应拦截器已解包 {code,data} → res.data 即报表数据(EfficiencyReport)
      let firstReport: EfficiencyReport | null = null;
      const items = await fetchAllPages<EfficiencyItem>(
        (params) => api.get('/reports/efficiency', { params }).then((res) => {
          const payload = res.data as EfficiencyReport;
          if (params.page === 1) firstReport = payload;
          return { data: payload };
        }),
        extraParams,
      );
      if (firstReport) {
        setReport({ ...firstReport, items, total: items.length });
      } else {
        message.warning('暂无能效数据');
      }
    } catch {
      message.error('加载能效数据失败');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadStations();
  }, []);

  useEffect(() => {
    if (selectedStation) {
      loadEfficiencyData(selectedStation, minEfficiency);
    }
  }, [selectedStation, minEfficiency, loadEfficiencyData]);

  const items = report?.items || [];
  const avgEfficiency = items.length
    ? items.reduce((sum, it) => sum + it.charge_efficiency, 0) / items.length
    : 0;

  const renderEfficiencyTag = (val: number) => (
    <Tag color={val >= 85 ? 'green' : val >= 70 ? 'orange' : 'red'}>
      {val.toFixed(1)}%
    </Tag>
  );

  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 筛选条件 */}
        <Col span={24}>
          <Space>
            <Select
              style={{ width: 200 }}
              placeholder="选择站点"
              value={selectedStation}
              onChange={setSelectedStation}
              options={stations.map(s => ({ label: s.name, value: s.id }))}
            />
            <InputNumber
              style={{ width: 160 }}
              min={0}
              max={100}
              value={minEfficiency}
              onChange={(v) => setMinEfficiency(v ?? 70)}
              formatter={v => `${v}%`}
              parser={(v) => Number((v || '').replace('%', '')) as number}
              placeholder="低效预警阈值"
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => loadEfficiencyData(selectedStation, minEfficiency)}
            >
              刷新
            </Button>
          </Space>
        </Col>

        {/* 概览 */}
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="设备总数"
              value={report?.total || 0}
              suffix="台"
              prefix={<BulbOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="平均充电效率"
              value={Number(avgEfficiency.toFixed(1))}
              suffix="%"
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="异常低效设备"
              value={report?.alerts?.abnormal_low_efficiency?.count || 0}
              suffix="台"
              prefix={<WarningOutlined />}
              valueStyle={{ color: (report?.alerts?.abnormal_low_efficiency?.count || 0) > 0 ? '#cf1322' : '#3f8600' }}
            />
          </Card>
        </Col>

        {/* 异常低效预警 */}
        <Col span={24}>
          <Card
            title={`异常低效设备预警 (阈值 ${report?.alerts?.abnormal_low_efficiency?.threshold || `<${minEfficiency}%`})`}
            loading={loading}
          >
            <List
              dataSource={report?.alerts?.abnormal_low_efficiency?.items || []}
              locale={{ emptyText: '无异常低效设备' }}
              renderItem={(item) => (
                <List.Item>
                  <Tag color="red">{item.charge_efficiency.toFixed(1)}%</Tag>
                  {item.device_name}
                  <Tag>{item.station_name || '-'}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 充电效率排名 */}
        <Col span={24}>
          <Card title="设备充电效率排名" loading={loading}>
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              dataSource={items}
              rowKey="device_id"
              pagination={false}
              columns={[
                { title: '设备名称', dataIndex: 'device_name', key: 'device_name' },
                { title: '设备编码', dataIndex: 'device_code', key: 'device_code' },
                { title: '所属站点', dataIndex: 'station_name', key: 'station_name' },
                {
                  title: '充电效率',
                  dataIndex: 'charge_efficiency',
                  key: 'charge_efficiency',
                  render: renderEfficiencyTag,
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default EfficiencyAnalysis;
