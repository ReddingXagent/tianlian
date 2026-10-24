/**
 * 天链 V3 - 站点管理页面（编码重构）
 * 
 * 重构：新增站点时选择区域，自动生成编码
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Table, Tag, Spin, Alert, Button, Modal, Form, Input, InputNumber, Select, Space, message, Popconfirm, Statistic, Row, Col } from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, ReloadOutlined, SearchOutlined, HomeOutlined, TeamOutlined } from '@ant-design/icons';
import { stationAPI, teamAPI } from '../../api';
import type { StationCreateRequest } from '../../types';
import PageWrapper from '../../components/PageWrapper';

const { Option } = Select;

interface Station {
  id: number;
  name: string;
  code: string;
  address?: string;
  total_power?: number;
  total_devices?: number;
  status: string;
  health_score?: number;
  description?: string;
  contact_phone?: string;
  contact_person?: string;
  created_at?: string;
  updated_at?: string;
}

const statusColors: Record<string, string> = {
  normal: 'green',
  maintenance: 'orange',
  closed: 'red',
};

const getStatusLabels = (t: (k: string) => string): Record<string, string> => ({
  normal: t('pages.stations.status_normal'),
  maintenance: t('pages.stations.status_maintenance'),
  closed: t('pages.stations.status_closed'),
});

// 区域码映射
const regionOptions = [
  { value: 'HN', label: '河南' },
  { value: 'GD', label: '广东' },
  { value: 'JS', label: '江苏' },
  { value: 'SD', label: '山东' },
  { value: 'ZJ', label: '浙江' },
  { value: 'FJ', label: '福建' },
  { value: 'SC', label: '四川' },
  { value: 'HB', label: '湖北' },
  { value: 'BJ', label: '北京' },
  { value: 'SH', label: '上海' },
  { value: 'GX', label: '广西' },
  { value: 'SN', label: '陕西' },
  { value: 'CQ', label: '重庆' },
  { value: 'LN', label: '辽宁' },
];

const Stations: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [stations, setStations] = useState<Station[]>([]);
  const [error, setError] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [assignVisible, setAssignVisible] = useState(false);
  const [assignStationId, setAssignStationId] = useState<number | null>(null);
  const [assignTeamId, setAssignTeamId] = useState<number | undefined>();
  const [teams, setTeams] = useState<{id: number; name: string}[]>([]);
  const [assignLoading, setAssignLoading] = useState(false);
  const [currentStation, setCurrentStation] = useState<Station | null>(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  
  /* ── 编码预览 ── */
  const [previewCode, setPreviewCode] = useState<string>('');

  useEffect(() => {
    fetchStations();
  }, []);

  const fetchStations = async () => {
    setLoading(true);
    try {
      const { data } = await stationAPI.list();
      setStations(Array.isArray(data) ? data : data.items || []);
      setError('');
    } catch (err: unknown) {
      setError('加载失败：' + ((err as any)?.response?.data?.detail || (err as any)?.message));
      message.error(t('pages.stations.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setCurrentStation(null);
    form.resetFields();
    form.setFieldsValue({ region: 'HN', status: 'normal' });  // 默认HN
    setPreviewCode(generatePreviewCode('HN'));
    setModalVisible(true);
  };

  const handleEdit = (record: Station) => {
    setCurrentStation(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await stationAPI.delete(id);
      message.success(t('pages.stations.delete_success'));
      fetchStations();
    } catch (err: unknown) {
      message.error(t('pages.stations.delete_failed') + '：' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    }
  };

  const handleOpenAssign = async (record: Station) => {
    setAssignStationId(record.id);
    setAssignTeamId(undefined);
    try {
      const { data: teamData } = await teamAPI.list();
      const items = Array.isArray(teamData) ? teamData : (teamData as any)?.items || [];
      setTeams(items.map((t: any) => ({ id: t.id, name: t.name })));
    } catch {
      setTeams([]);
    }
    setAssignVisible(true);
  };

  const handleAssign = async () => {
    if (!assignStationId || !assignTeamId) return;
    setAssignLoading(true);
    try {
      await stationAPI.assign(assignStationId, assignTeamId);
      message.success('站点已分配团队');
      setAssignVisible(false);
      fetchStations();
    } catch (err: unknown) {
      message.error('分配失败：' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    } finally {
      setAssignLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (currentStation) {
        await stationAPI.update(currentStation.id, values);
        message.success(t('pages.stations.update_success'));
      } else {
        // 新增站点，传入region参数
        const createData: StationCreateRequest = {
          name: values.name,
          code: previewCode || generatePreviewCode(values.region || 'HN'),
          region: values.region || 'HN',
          province: values.province,
          city: values.city,
          district: values.district,
          address: values.address,
          total_power: values.total_power,
          gun_count: values.gun_count,
          status: values.status,
          contact_person: values.contact_person,
          contact_phone: values.contact_phone,
          description: values.description,
          pv_capacity: values.pv_capacity,
          ess_capacity: values.ess_capacity,
        };
        const res = await stationAPI.create(createData);
        message.success(`站点已创建，编码: ${(res as any)?.data?.code || '已生成'}`);
      }
      setModalVisible(false);
      setPreviewCode('');
      fetchStations();
    } catch (err: unknown) {
      if ((err as any)?.errorFields) return;
      message.error('操作失败：' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    }
  };

  const handleDetail = (record: Station) => {
    setCurrentStation(record);
    setDetailVisible(true);
  };

  /* ── 生成编码预览 ── */
  const generatePreviewCode = (region: string) => {
    // 预览格式: Z + 区域码 + 示例序号
    return `Z${region}0001`;
  };

  /* ── 区域变化时更新预览 ── */
  const handleRegionChange = (region: string) => {
    setPreviewCode(generatePreviewCode(region));
  };

  const filteredStations = stations.filter(s => {
    const matchSearch = !searchText || 
      s.name.toLowerCase().includes(searchText.toLowerCase()) ||
      s.code.toLowerCase().includes(searchText.toLowerCase());
    const matchStatus = !statusFilter || s.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const stats = {
    total: stations.length,
    normal: stations.filter(s => s.status === 'normal').length,
    maintenance: stations.filter(s => s.status === 'maintenance').length,
    closed: stations.filter(s => s.status === 'closed').length,
  };

  const columns = [
    { 
      title: t('pages.stations.code'), 
      dataIndex: 'code', 
      key: 'code',
      width: 120,
      render: (code: string) => code ? <Tag color="blue">{code}</Tag> : '-',
    },
    { 
      title: '利用率', 
      dataIndex: 'utilization_rate', 
      key: 'utilization_rate',
      width: 90,
      render: (v: number | null) => (v == null ? '-' : `${v}%`),
    },
    { 
      title: t('pages.stations.name'), 
      dataIndex: 'name', 
      key: 'name',
      width: 180,
    },
    { 
      title: t('app.address'), 
      dataIndex: 'address', 
      key: 'address',
      ellipsis: true,
    },
    { 
      title: t('pages.stations.power'), 
      dataIndex: 'total_power', 
      key: 'total_power',
      width: 100,
      align: 'right' as const,
    },
    { 
      title: t('pages.stations.device_count'), 
      dataIndex: 'total_devices', 
      key: 'total_devices',
      width: 80,
      align: 'right' as const,
    },
    { 
      title: t('pages.stations.health_score'), 
      dataIndex: 'health_score', 
      key: 'health_score',
      width: 90,
      align: 'right' as const,
      render: (v: number) => {
        if (v == null) return '-';
        const color = v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red';
        return <span style={{ color }}>{v}</span>;
      }
    },
    { 
      title: t('app.status'), 
      dataIndex: 'status', 
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={statusColors[v] || 'default'}>{getStatusLabels(t)[v] || v}</Tag>
      ),
    },
    {
      title: t('app.action'),
      key: 'action',
      width: 240,
      render: (_: unknown, record: Station) => (
        <Space>
          <Button size="small" icon={<TeamOutlined />} onClick={() => handleOpenAssign(record)}>{t('pages.stations.assign_team')}</Button>
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleDetail(record)}>{t('app.detail')}</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>{t('app.edit')}</Button>
          <Popconfirm title={t('pages.stations.delete_confirm')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>{t('app.delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      loading={loading && stations.length === 0}
      skeletonType="table"
      skeletonCount={6}
      hasData={stations.length > 0}
      empty={{
        type: 'default',
        title: '暂无站点',
        description: '尚未添加任何站点，点击下方按钮开始添加',
        actionText: '添加站点',
        onAction: handleCreate,
      }}
      error={error && stations.length === 0 ? error : null}
      onRetry={fetchStations}
      transition="slide-up"
    >
    <div className="page-container">
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title={t('pages.stations.total')} value={stats.total} prefix={<HomeOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('pages.stations.normal_status')} value={stats.normal} valueStyle={{ color: '#34a853' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('pages.stations.maintenance_status')} value={stats.maintenance} valueStyle={{ color: '#f5a623' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('pages.stations.closed_status')} value={stats.closed} valueStyle={{ color: '#ea4335' }} />
          </Card>
        </Col>
      </Row>

      <Card 
        title={t('pages.stations.list')}
        extra={
          <Space>
            <Input
              placeholder={t('pages.stations.search_placeholder')}
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
            <Select
              placeholder={t('app.status_filter')}
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={setStatusFilter}
            >
              <Option value="normal">{t('pages.stations.status_normal')}</Option>
              <Option value="maintenance">{t('pages.stations.status_maintenance')}</Option>
              <Option value="closed">{t('pages.stations.status_closed')}</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={fetchStations}>{t('app.refresh')}</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>{t('pages.stations.add')}</Button>
          </Space>
        }
      >
        <AutoHeightTable
          scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
          columns={columns}
          dataSource={filteredStations}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => t('app.total', { count: total }) }}
        />
      </Card>

      {/* 创建/编辑弹窗 */}
      <Modal
        title={currentStation ? t('pages.stations.edit') : t('pages.stations.add')}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setModalVisible(false);
          setPreviewCode('');
        }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label={t('pages.stations.name')} rules={[{ required: true, message: t('pages.stations.name_required') }]}>
                <Input placeholder={t('pages.stations.name_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item 
                name="region" 
                label={t('pages.stations.region')} 
                rules={currentStation ? [] : [{ required: true, message: '请选择区域' }]}
                initialValue="HN"
              >
                <Select 
                  placeholder={t('pages.stations.region_placeholder')}
                  onChange={handleRegionChange}
                  disabled={!!currentStation}
                  showSearch
                  optionFilterProp="label"
                >
                  {regionOptions.map(opt => (
                    <Select.Option key={opt.value} value={opt.value} label={opt.label}>
                      {opt.label} ({opt.value})
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          
          {/* 编码预览 */}
          {!currentStation && (
            <Alert 
              message={t('pages.stations.preview_code', { code: previewCode })}
              description={t('pages.stations.code_format')}
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
          
          <Form.Item name="address" label={t('app.address')}>
            <Input placeholder={t('pages.stations.address_placeholder')} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="province" label={t('pages.stations.province')}>
                <Input placeholder={t('pages.stations.province_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="city" label={t('pages.stations.city')}>
                <Input placeholder={t('pages.stations.city_placeholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="pv_capacity" label="光伏装机量(kWp)">
                <InputNumber style={{ width: '100%' }} min={0} step={0.1} placeholder="如 120" />
              </Form.Item>
              <Form.Item name="ess_capacity" label="储能装机量(kWh)">
                <InputNumber style={{ width: '100%' }} min={0} step={0.1} placeholder="如 200" />
              </Form.Item>
              <Form.Item name="total_power" label={t('pages.stations.total_power')}>
                <InputNumber style={{ width: '100%' }} placeholder={t('pages.stations.power_placeholder')} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="gun_count" label={t('pages.stations.gun_count')}>
                <InputNumber style={{ width: '100%' }} placeholder={t('pages.stations.gun_placeholder')} min={0} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="status" label={t('app.status')} rules={[{ required: true, message: t('app.select_status') }]} initialValue="normal">
            <Select placeholder={t('app.select_status')}>
              <Option value="normal">{t('pages.stations.status_normal')}</Option>
              <Option value="maintenance">{t('pages.stations.status_maintenance')}</Option>
              <Option value="closed">{t('pages.stations.status_closed')}</Option>
            </Select>
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="contact_person" label={t('pages.stations.contact_person')}>
                <Input placeholder={t('pages.stations.contact_placeholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contact_phone" label={t('pages.stations.contact_phone')}>
                <Input placeholder={t('pages.stations.phone_placeholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label={t('app.description')}>
            <Input.TextArea rows={3} placeholder={t('pages.stations.desc_placeholder')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title={t('pages.stations.detail')}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>{t('app.close')}</Button>
        ]}
        width={600}
      >
        {currentStation && (
          <div>
            <p><strong>{t('pages.stations.code')}：</strong>{currentStation.code ? <Tag color="blue">{currentStation.code}</Tag> : '-'}</p>
            <p><strong>{t('pages.stations.name')}：</strong>{currentStation.name}</p>
            <p><strong>{t('app.address')}：</strong>{currentStation.address || '-'}</p>
            <p><strong>{t('pages.stations.total_power')}：</strong>{currentStation.total_power || '-'} kW</p>
            <p><strong>{t('pages.stations.device_count')}：</strong>{currentStation.total_devices || '-'}</p>
            <p><strong>{t('pages.stations.health_score')}：</strong>{currentStation.health_score != null ? currentStation.health_score : '-'}</p>
            <p><strong>{t('app.status')}：</strong><Tag color={statusColors[currentStation.status]}>{getStatusLabels(t)[currentStation.status]}</Tag></p>
            <p><strong>{t('pages.stations.contact_person')}：</strong>{currentStation.contact_person || '-'}</p>
            <p><strong>{t('pages.stations.contact_phone')}：</strong>{currentStation.contact_phone || '-'}</p>
            <p><strong>{t('app.description')}：</strong>{currentStation.description || '-'}</p>
            <p><strong>{t('app.created_at')}：</strong>{currentStation.created_at || '-'}</p>
            <p><strong>{t('app.updated_at')}：</strong>{currentStation.updated_at || '-'}</p>
          </div>
        )}
      </Modal>

      {/* 分配团队弹窗 */}
      <Modal
        title={t('pages.stations.assign_team')}
        open={assignVisible}
        onOk={handleAssign}
        onCancel={() => setAssignVisible(false)}
        confirmLoading={assignLoading}
      >
        <div style={{ marginBottom: 16 }}>
          <p><strong>{t('pages.stations.name')}：</strong>{stations.find(s => s.id === assignStationId)?.name}</p>
        </div>
        <Select
          placeholder={t('pages.stations.select_team')}
          style={{ width: '100%' }}
          value={assignTeamId}
          onChange={setAssignTeamId}
          showSearch
          optionFilterProp="label"
        >
          {teams.map(t => (
            <Select.Option key={t.id} value={t.id} label={t.name}>
              {t.name}
            </Select.Option>
          ))}
        </Select>
      </Modal>
    </div>
    </PageWrapper>
  );
};

export default Stations;