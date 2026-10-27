/**
 * 告警管理页面（筑基1增强版）
 */
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Row, Col, Table, Tag, Button, Select, Space, Statistic, Progress, Modal, Form, Input, DatePicker, message, Popconfirm, Descriptions, Tabs, Spin } from 'antd';
import { 
  AlertOutlined, WarningOutlined, 
  ExclamationCircleOutlined, CheckCircleOutlined, SyncOutlined, FilterOutlined, InfoCircleOutlined,
  ClearOutlined, EyeOutlined, SettingOutlined
} from '@ant-design/icons';
import { alarmAPI } from '../../api';
import { useIsMobile } from '../../hooks/useIsMobile';
import type { Alarm } from '../../types';
import AlarmRulesTab from './AlarmRules';

const { RangePicker } = DatePicker;
const { TextArea } = Input;

const AlarmListPage: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState('all');
  const [level, setLevel] = useState('all');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [handleModalVisible, setHandleModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedAlarm, setSelectedAlarm] = useState<Alarm | null>(null);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ total: 0, critical: 0, warning: 0, handled: 0 });
  const [form] = Form.useForm();

  // 移动端响应式：Modal 自适应宽度 + 筛选器折叠 + 表格/卡片切换
  const isMobile = useIsMobile();
  const modalFullWidth = 'calc(100vw - 24px)';
  const [filtersOpen, setFiltersOpen] = useState(false);

  // 获取告警数据
  const fetchAlarms = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (status !== 'all') params.status = status;
      if (level !== 'all') params.level = level;
      if (dateRange) { params.start_date = dateRange[0]; params.end_date = dateRange[1]; }
      
      const res = await alarmAPI.list(params);
      const resData = res.data as any;
      const alarmList: Alarm[] = resData?.items || (Array.isArray(resData) ? resData : []);
      
      setAlarms(alarmList.map((a: Alarm) => ({
        ...a,
        id: Number(a.id),
      })) as Alarm[]);
      
      // 获取统计数据
      try {
        const statsRes = await alarmAPI.stats();
        const sd = statsRes.data as any;
        setStats({
          total: sd?.total || alarmList.length,
          critical: sd?.critical || alarmList.filter((a: Alarm) => a.level === 'critical').length,
          warning: sd?.warning || alarmList.filter((a: Alarm) => (a as any).level === 'warning').length,
          handled: sd?.resolved || alarmList.filter((a: Alarm) => a.status === 'resolved').length,
        });
      } catch {
        setStats({
          total: alarmList.length,
          critical: alarmList.filter((a: Alarm) => a.level === 'critical').length,
          warning: alarmList.filter((a: Alarm) => (a as any).level === 'warning').length,
          handled: alarmList.filter((a: Alarm) => a.status === 'resolved').length,
        });
      }
    } catch (error) {
      message.error(t('pages.alarms.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlarms();
  }, [status, level]);

  const getLevelTag = (lvl: string) => {
    const tags: Record<string, { color: string; text: string }> = {
      critical: { color: 'red', text: t('pages.alarms.level_critical') },
      warning: { color: 'orange', text: t('pages.alarms.level_warning') },
      info: { color: 'blue', text: t('pages.alarms.level_info') },
    };
    return tags[lvl] || { color: 'default', text: lvl };
  };

  const getStatusTag = (st: string) => {
    const tags: Record<string, { color: string; text: string }> = {
      pending: { color: 'red', text: t('pages.alarms.status_pending') },
      handling: { color: 'orange', text: t('pages.alarms.status_handling') },
      resolved: { color: 'green', text: t('pages.alarms.status_resolved') },
      ignored: { color: 'default', text: t('pages.alarms.status_ignored') },
    };
    return tags[st] || { color: 'default', text: st };
  };

  const handleAlarm = (record: Alarm) => {
    setSelectedAlarm(record);
    setHandleModalVisible(true);
  };

  const handleAck = async (record: Alarm) => {
    try {
      await alarmAPI.ack(record.id);
      message.success(t('pages.alarms.acknowledged'));
      fetchAlarms();
    } catch {
      message.error(t('pages.alarms.ack_failed'));
    }
  };

  const handleResolve = async (record: Alarm) => {
    try {
      await alarmAPI.resolve(record.id);
      message.success(t('pages.alarms.resolved'));
      fetchAlarms();
    } catch {
      message.error(t('pages.alarms.resolve_failed'));
    }
  };

  /** 行内操作按钮 —— 桌面表格操作列与移动卡片底部共用，避免移动端功能退化 */
  const renderActions = (record: Alarm) => (
    <Space>
      <Button
        size="small"
        icon={<EyeOutlined />}
        onClick={() => {
          setSelectedAlarm(record);
          setDetailModalVisible(true);
        }}
      >
        详情
      </Button>
      {record.status !== 'resolved' && (
        <>
          <Button size="small" onClick={() => handleAck(record)}>
            确认
          </Button>
          <Button size="small" type="primary" onClick={() => handleAlarm(record)}>
            处理
          </Button>
        </>
      )}
    </Space>
  );

  // ── 筛选控件（桌面常驻 / 移动端折叠；刷新按钮常驻） ──
  const filterControls = (
    <>
      <Select value={status} onChange={setStatus} style={{ width: 120 }}>
        <Select.Option value="all">{t('pages.alarms.filter_all_status')}</Select.Option>
        <Select.Option value="active">{t('pages.alarms.status_active')}</Select.Option>
        <Select.Option value="acknowledged">{t('pages.alarms.status_acknowledged')}</Select.Option>
        <Select.Option value="processing">{t('pages.alarms.status_processing')}</Select.Option>
        <Select.Option value="resolved">{t('pages.alarms.status_resolved')}</Select.Option>
        <Select.Option value="ignored">{t('pages.alarms.status_ignored')}</Select.Option>
      </Select>
      <Select value={level} onChange={setLevel} style={{ width: 120 }}>
        <Select.Option value="all">{t('pages.alarms.filter_all_level')}</Select.Option>
        <Select.Option value="critical">{t('pages.alarms.level_critical')}</Select.Option>
        <Select.Option value="warning">{t('pages.alarms.level_warning')}</Select.Option>
        <Select.Option value="info">{t('pages.alarms.level_info')}</Select.Option>
      </Select>
      <RangePicker onChange={(dates: any) => {
        if (dates && dates[0] && dates[1]) {
          setDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]);
        } else { setDateRange(null); }
      }} />
      <Popconfirm title={t('pages.alarms.confirm_batch_clear')} onConfirm={async () => {
        try {
          await Promise.all(selectedRowKeys.map(id => alarmAPI.ignore(id)));
          message.success(t('pages.alarms.batch_cleared', { count: selectedRowKeys.length }));
          setSelectedRowKeys([]);
          fetchAlarms();
        } catch { message.error(t('pages.alarms.batch_clear_failed')); }
      }}>
        <Button icon={<ClearOutlined />} danger disabled={selectedRowKeys.length === 0}>
          {t('pages.alarms.batch_clear')} {selectedRowKeys.length > 0 && `(${selectedRowKeys.length})`}
        </Button>
      </Popconfirm>
    </>
  );
  const refreshBtn = <Button icon={<SyncOutlined />} onClick={fetchAlarms}>{t('app.refresh')}</Button>;

  const columns = [
    { 
      title: t('pages.alarms.level'), 
      dataIndex: 'level', 
      key: 'level',
      width: 100,
      filters: [
        { text: t('pages.alarms.level_critical'), value: 'critical' },
        { text: t('pages.alarms.level_warning'), value: 'warning' },
        { text: t('pages.alarms.level_info'), value: 'info' },
      ],
      onFilter: (value: string | number | boolean, record: Alarm) => record.level === value,
      render: (lvl: string) => {
        const tag = getLevelTag(lvl);
        return (
          <Space>
            {lvl === 'critical' && <ExclamationCircleOutlined style={{ color: '#ea4335' }} />}
            {lvl === 'warning' && <WarningOutlined style={{ color: '#f5a623' }} />}
            {lvl === 'info' && <InfoCircleOutlined style={{ color: '#ff5a36' }} />}
            <Tag color={tag.color}>{tag.text}</Tag>
          </Space>
        );
      }
    },
    { title: t('pages.alarms.device'), dataIndex: 'device_name', key: 'device_name', width: 150, ellipsis: true },
    { title: t('pages.alarms.alarm_type'), dataIndex: 'title', key: 'title', width: 120 },
    { title: t('pages.alarms.station'), dataIndex: 'station_name', key: 'station_name', width: 120 },
    { title: t('app.time'), dataIndex: 'created_at', key: 'created_at', width: 180 },
    { title: t('app.description'), dataIndex: 'description', key: 'description', ellipsis: true },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status',
      width: 100,
      filters: [
        { text: t('pages.alarms.status_active'), value: 'active' },
        { text: t('pages.alarms.status_acknowledged'), value: 'acknowledged' },
        { text: t('pages.alarms.status_processing'), value: 'processing' },
        { text: t('pages.alarms.status_resolved'), value: 'resolved' },
        { text: t('pages.alarms.status_ignored'), value: 'ignored' },
      ],
      onFilter: (value: string | number | boolean, record: Alarm) => record.status === value,
      render: (st: string) => {
        const tag = getStatusTag(st);
        return <Tag color={tag.color}>{tag.text}</Tag>;
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      fixed: 'right' as const,
      render: (_: unknown, record: Alarm) => renderActions(record),
    },
  ];

  const handleProcessSubmit = async (values: { action: string; remark?: string }) => {
    try {
      if (values.action === 'resolve') {
        await alarmAPI.resolve(selectedAlarm.id);
        message.success(t('pages.alarms.resolved'));
      } else {
        await alarmAPI.ack(selectedAlarm.id);
        message.success(t('pages.alarms.acknowledged'));
      }
      setHandleModalVisible(false);
      fetchAlarms();
    } catch {
      message.error('操作失败');
    }
  };

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title={t('pages.alarms.total_count')} value={stats.total} prefix={<AlertOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title={t('pages.alarms.critical_count')} value={stats.critical} prefix={<ExclamationCircleOutlined style={{ color: '#ea4335' }} />} valueStyle={{ color: '#ea4335' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title={t('pages.alarms.warning_count')} value={stats.warning} prefix={<WarningOutlined style={{ color: '#f5a623' }} />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title={t('pages.alarms.handled_count')} value={stats.handled} prefix={<CheckCircleOutlined style={{ color: '#34a853' }} />} />
            <Progress percent={stats.total > 0 ? Math.round((stats.handled / stats.total) * 100) : 0} showInfo={false} strokeColor="#34a853" />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="list" items={[
        {
          key: 'list',
          label: <Space><AlertOutlined />{t('pages.alarms.list')}</Space>,
          children: (
            <Card>
              {/* 筛选栏：桌面常驻 / 移动端折叠（刷新按钮常驻） */}
              {isMobile ? (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {refreshBtn}
                    <Button
                      size="small"
                      type={filtersOpen ? 'primary' : 'default'}
                      icon={<FilterOutlined />}
                      onClick={() => setFiltersOpen(o => !o)}
                    >
                      筛选
                    </Button>
                  </div>
                  {filtersOpen && (
                    <div style={{ marginTop: 8 }}>
                      <Space wrap>{filterControls}</Space>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ marginBottom: 16 }}>
                  <Space wrap>
                    {refreshBtn}
                    {filterControls}
                  </Space>
                </div>
              )}

              {/* 列表：移动端卡片 / 桌面表格（横向滚动） */}
              {isMobile ? (
                loading ? (
                  <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>
                ) : (
                  <div>
                    {alarms.map(record => {
                      const lvl = getLevelTag(record.level);
                      const st = getStatusTag(record.status);
                      // AlarmLevel 联合(critical/major/minor/info)无 'warning'，转 string 与桌面 columns render(lvl:string) 行为一致
                      const levelStr = String(record.level);
                      return (
                        <Card
                          key={record.id}
                          size="small"
                          data-testid="alarm-mobile-card"
                          style={{ marginBottom: 8 }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <Space>
                              {levelStr === 'critical' && <ExclamationCircleOutlined style={{ color: '#ea4335' }} />}
                              {levelStr === 'warning' && <WarningOutlined style={{ color: '#f5a623' }} />}
                              {levelStr === 'info' && <InfoCircleOutlined style={{ color: '#ff5a36' }} />}
                              <Tag color={lvl.color}>{lvl.text}</Tag>
                              <strong>{record.device_name}</strong>
                            </Space>
                            <Tag color={st.color}>{st.text}</Tag>
                          </div>
                          <div style={{ marginBottom: 6 }}>{record.title}</div>
                          <Space size={4} wrap style={{ marginBottom: 8 }}>
                            <span>{record.station_name}</span>
                            <span style={{ color: '#999', fontSize: 12 }}>{record.created_at}</span>
                          </Space>
                          {renderActions(record)}
                        </Card>
                      );
                    })}
                  </div>
                )
              ) : (
                <div className="table-scroll-x">
                <Table
                  columns={columns}
                  dataSource={alarms}
                  rowKey="id"
                  loading={loading}
                  rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as number[]) }}
                  pagination={{ total: alarms.length, pageSize: 10, showTotal: (total) => t('app.total', { count: total }) }}
                  scroll={{ x: 900 }}
                />
                </div>
              )}
            </Card>
          ),
        },
        {
          key: 'rules',
          label: <Space><SettingOutlined />{t('pages.alarms.rules')}</Space>,
          children: <AlarmRulesTab />,
        },
      ]} />

      {/* 处理告警弹窗 */}
      <Modal
        title={t('pages.alarms.process_alarm')}
        open={handleModalVisible}
        width={isMobile ? modalFullWidth : 520}
        onCancel={() => setHandleModalVisible(false)}
        footer={[
          <Button key="submit" type="primary" onClick={() => form.submit()}>{t('pages.alarms.confirm_process')}</Button>,
          <Button key="back" onClick={() => setHandleModalVisible(false)}>{t('app.cancel')}</Button>,
        ]}
      >
        {selectedAlarm && (
          <Form layout="vertical" form={form} onFinish={handleProcessSubmit}>
            <Form.Item label={t('pages.alarms.device')}>
              <Input value={selectedAlarm.device_name || ''} disabled />
            </Form.Item>
            <Form.Item label={t('pages.alarms.alarm_type')}>
              <Input value={selectedAlarm.title} disabled />
            </Form.Item>
            <Form.Item label={t('pages.alarms.level')}>
              <Tag color={getLevelTag(selectedAlarm.level).color}>
                {getLevelTag(selectedAlarm.level).text}
              </Tag>
            </Form.Item>
            <Form.Item label={t('pages.alarms.handle_status')} name="action" initialValue="resolve">
              <Select>
                <Select.Option value="resolve">{t('pages.alarms.status_resolved')}</Select.Option>
                <Select.Option value="ack">{t('pages.alarms.confirm_process')}</Select.Option>
                <Select.Option value="ignore">{t('pages.alarms.status_ignored')}</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item label={t('app.remark')} name="remark">
              <TextArea rows={4} placeholder={t('pages.alarms.remark_placeholder')} />
            </Form.Item>
          </Form>
        )}
      </Modal>

      {/* 告警详情弹窗 */}
      <Modal
        title={t('pages.alarms.detail')}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>{t('app.close')}</Button>,
        ]}
        width={isMobile ? modalFullWidth : 700}
      >
        {selectedAlarm && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label={t('pages.alarms.device')}>{selectedAlarm.device_name || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('pages.alarms.station')}>{selectedAlarm.station_name || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('pages.alarms.alarm_type')}>{selectedAlarm.title}</Descriptions.Item>
            <Descriptions.Item label={t('pages.alarms.level')}>
              <Tag color={getLevelTag(selectedAlarm.level).color}>
                {getLevelTag(selectedAlarm.level).text}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('app.status')}>
              <Tag color={getStatusTag(selectedAlarm.status).color}>
                {getStatusTag(selectedAlarm.status).text}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('app.time')}>{selectedAlarm.created_at}</Descriptions.Item>
            <Descriptions.Item label={t('app.description')} span={2}>{selectedAlarm.description || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default AlarmListPage;
