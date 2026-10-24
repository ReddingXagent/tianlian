/**
 * 设备管理页面 - 数据库版
 */
import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { 
  Card, Table, Button, Space, Input, Select, Tag, Modal, Spin,
  Form, Row, Col, message, Popconfirm, Badge, Avatar, Tooltip, AutoComplete
} from 'antd';
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  ReloadOutlined, ExportOutlined, DesktopOutlined, FilterOutlined,
  UpCircleOutlined
} from '@ant-design/icons';
import { deviceAPI, efficiencyAPI, deviceLibraryAPI, stationAPI, fetchAllPages } from '../../api';
import { useIsMobile } from '../../hooks/useIsMobile';
import type { PaginatedData } from '../../types';
import PageWrapper from '../../components/PageWrapper';
import AutoHeightTable from '../../components/AutoHeightTable';
import DeviceControlPanel from './DeviceControlPanel';
import DeviceConfigPanel from './DeviceConfigPanel';
import DeviceEfficiencyDetail from './DeviceEfficiencyDetail';
import FirmwareUpgradeModal from './components/FirmwareUpgradeModal';

const { Option } = Select;

interface Device {
  id: number;
  sn: string;
  name: string;
  code: string;
  type: string;
  model: string;
  manufacturer: string;
  protocol_type?: string;
  station_name?: string;
  station_id: number;
  status: string;
  health_score: number;
  utilization_rate?: number;
  created_at: string;
  updated_at: string;
}

// Re-export for type usage
export type { Device };

const DeviceListPage: React.FC = () => {
  const { t } = useTranslation();
  const [devices, setDevices] = useState<Device[]>([]);
  // 设备库联动（2026-10-09 丁哥：品牌/型号/协议下拉）
  const [libEntries, setLibEntries] = useState<any[]>([]);
  const [curBrand, setCurBrand] = useState<string>('');
  const [stationOptions, setStationOptions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [configVisible, setConfigVisible] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [firmwareVisible, setFirmwareVisible] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [form] = Form.useForm();
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // 每页条数自适应（2026-10-09 丁哥: PC大屏底部留白浪费 → 按视口高度算行数; 手动改过则停止干预）
  const calcAdaptivePageSize = () => {
    if (typeof window === 'undefined') return 20;
    const rows = Math.floor((window.innerHeight - 320) / 55);
    return Math.min(50, Math.max(10, rows));
  };
  const manualPageSize = useRef(false);
  const [pageSize, setPageSize] = useState(calcAdaptivePageSize);
  useEffect(() => {
    const onResize = () => {
      if (manualPageSize.current) return;
      setPageSize((p) => {
        const n = calcAdaptivePageSize();
        return p === n ? p : n;
      });
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  
  // 筛选条件
  const [filters, setFilters] = useState({
    search: '',
    type: '',
    status: '',
    station_id: '',
  });

  // 移动端响应式：Modal 自适应宽度 + 表格/卡片切换（筛选器已 Row/Col 响应式）
  const isMobile = useIsMobile();
  const modalFullWidth = 'calc(100vw - 24px)';

  useEffect(() => {
    fetchDevices();
  }, [page, pageSize, filters]);

  // 支持外部跳转定位: ?deviceId=<id> 自动打开设备详情
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    const deviceIdParam = searchParams.get('deviceId');
    if (!deviceIdParam) return;
    const targetId = Number(deviceIdParam);
    const found = devices.find((d) => d.id === targetId);
    if (found) {
      setSelectedDevice(found);
      setDetailVisible(true);
      // 定位完成后清理 URL, 避免刷新重复弹窗
      const next = new URLSearchParams(searchParams);
      next.delete('deviceId');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, devices, setSearchParams]);

  // 批量获取设备利用率数据
  const [utilizationMap, setUtilizationMap] = useState<Record<number, number>>({});

  useEffect(() => {
    const fetchUtilization = async () => {
      try {
        const res = await efficiencyAPI.utilization();
        const data = res.data as any;
        // Try to extract per-device utilization from warnings or dedicated fields
        const map: Record<number, number> = {};
        if (data?.warnings) {
          data.warnings.forEach((w: any) => {
            if (w.device_id != null) {
              map[w.device_id] = w.utilization_rate;
            }
          });
        }
        if (data?.device_utilization) {
          data.device_utilization.forEach((d: any) => {
            map[d.device_id] = d.utilization_rate;
          });
        }
        setUtilizationMap(map);
      } catch {
        // Silent fail - utilization is supplementary data
      }
    };
    fetchUtilization();
  }, []);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (filters.type) params.type = filters.type;
      if (filters.status) params.status = filters.status;
      if (filters.station_id) params.station_id = filters.station_id;
      if (filters.search) params.search = filters.search;
      
      const response = await deviceAPI.list(params);
      const respData = response.data as PaginatedData<Device>;
      
      setDevices(respData.items || []);
      setTotal(respData.total || 0);
    } catch (error: unknown) {
      message.error(t('pages.devices.load_failed') + ': ' + ((error as any)?.response?.data?.detail || (error as any)?.message));
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setSelectedDevice(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record: Device) => {
    setSelectedDevice(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  useEffect(() => {
    // 卡 971f853e: page_size 契约 le=100, 手拼 500/100 会 422 或静默截断 → fetchAllPages 循环拉全量
    fetchAllPages<any>((params) => deviceLibraryAPI.list(params))
      .then((items) => setLibEntries(items))
      .catch(() => {/* 设备库不可用时退化自由输入, 提示但不阻断 */ message.error('设备库加载失败，品牌型号将改为自由输入'); });
    // 站点下拉（2026-10-09 丁哥: 所属站点点击进入该站点设备管理）
    fetchAllPages<any>((params) => stationAPI.list(params))
      .then((items) => setStationOptions(items))
      .catch(() => message.error('站点列表加载失败'));
  }, []);

  const brandOptions = Array.from(new Set(libEntries.map((e: any) => e.brand).filter(Boolean)));
  const modelOptions = Array.from(new Set(
    libEntries.filter((e: any) => !curBrand || e.brand === curBrand)
      .map((e: any) => e.model).filter(Boolean)
  ));
  const protocolOptions = ['modbus_rtu', 'mqtt', 'modbus_tcp', 'can', 'opcua', 'ykc', 'szbus'];

  const handleDelete = async (id: number) => {
    try {
      await deviceAPI.delete(id);
      message.success(t('pages.devices.delete_success'));
      fetchDevices();
    } catch (error: unknown) {
      message.error(t('pages.devices.delete_failed') + ': ' + ((error as any)?.response?.data?.detail || (error as any)?.message));
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      // 设备库没有则自动新建（2026-10-09 丁哥需求）：brand+model 组合缺失时补建设备库条目
      if (values.manufacturer && values.model) {
        const exists = libEntries.some(
          (e: any) => e.brand === values.manufacturer && e.model === values.model
        );
        if (!exists) {
          try {
            await deviceLibraryAPI.create({
              brand: values.manufacturer,
              model: values.model,
              device_type: values.type ? String(values.type).toLowerCase() : undefined,
              supported_protocols: values.protocol_type ? [values.protocol_type] : [],
            });
            message.info(`已同步新建设备库条目: ${values.manufacturer} ${values.model}`);
          } catch { /* 设备库写入失败不阻塞设备保存 */ }
        }
      }
      if (selectedDevice) {
        await deviceAPI.update(selectedDevice.id, values);
        message.success(t('pages.devices.update_success'));
      } else {
        await deviceAPI.create(values);
        message.success(t('pages.devices.create_success'));
      }
      setModalVisible(false);
      fetchDevices();
    } catch (error: unknown) {
      message.error('操作失败: ' + ((error as any)?.response?.data?.detail || (error as any)?.message));
    }
  };

  const statusColorMap: Record<string, string> = {
    ONLINE: 'green',
    OFFLINE: 'red',
    CHARGING: 'blue',
    FAULT: 'orange',
    MAINTENANCE: 'gold',
  };

  const statusTextMap: Record<string, string> = {
    ONLINE: t('pages.devices.status_online'),
    OFFLINE: t('pages.devices.status_offline'),
    CHARGING: t('pages.devices.status_charging'),
    FAULT: t('pages.devices.status_fault'),
    MAINTENANCE: t('pages.devices.status_maintenance'),
  };

  const typeTextMap: Record<string, string> = {
    CHARGER_DC: t('pages.devices.type_charger_dc'),
    CHARGER_AC: t('pages.devices.type_charger_ac'),
    V2G_CHARGER: 'V2G充电桩',
    PV_INVERTER: t('pages.devices.type_pv_inverter'),
    BATTERY_INVERTER: t('pages.devices.type_battery_inverter'),
    PCS: t('pages.devices.type_pcs'),
    BATTERY: t('pages.devices.type_battery'),
    METER: t('pages.devices.type_meter'),
    GATEWAY: t('pages.devices.type_gateway'),
  };

  /** 行内操作按钮 —— 桌面表格操作列与移动卡片底部共用，避免移动端功能退化 */
  const renderActions = (record: Device) => (
    <Space size="small">
      <Button
        type="link"
        size="small"
        onClick={() => {
          setSelectedDevice(record);
          setDetailVisible(true);
        }}
      >
        详情
      </Button>
      <Button
        type="link"
        size="small"
        onClick={() => {
          setSelectedDevice(record);
          setConfigVisible(true);
        }}
      >
        参数
      </Button>
      <Button
        type="link"
        size="small"
        icon={<UpCircleOutlined />}
        onClick={() => {
          setSelectedDevice(record);
          setFirmwareVisible(true);
        }}
      >
        固件
      </Button>
      <Button
        type="link"
        size="small"
        icon={<EditOutlined />}
        onClick={() => handleEdit(record)}
      >
        编辑
      </Button>
      <Popconfirm
        title={t('pages.devices.confirm_delete')}
        onConfirm={() => handleDelete(record.id)}
      >
        <Button type="link" size="small" danger icon={<DeleteOutlined />}>
          删除
        </Button>
      </Popconfirm>
    </Space>
  );

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: t('pages.devices.name'), dataIndex: 'name', key: 'name', width: 150, 
      render: (text: string, record: Device) => (
        <Space>
          <DesktopOutlined />
          <span className="cell-hscroll" title={text}>{text}</span>
        </Space>
      ),
    },
    { title: t('pages.devices.code'), dataIndex: 'code', key: 'code', width: 120 },
    { 
      title: t('pages.devices.type'), 
      dataIndex: 'type', 
      key: 'type', 
      width: 120,
      render: (type: string) => typeTextMap[(type || '').toUpperCase()] || typeTextMap[type] || type,
    },
    { title: t('pages.devices.model'), dataIndex: 'model', key: 'model', width: 120,
      render: (text: string) => <span className="cell-hscroll" title={text}>{text || '-'}</span>,
    },
    { title: t('pages.devices.manufacturer'), dataIndex: 'manufacturer', key: 'manufacturer', width: 100 },
    {
      title: '所属站点',
      dataIndex: 'station_name',
      key: 'station_name',
      width: 130,
      render: (text: string, record: Device) => (
        <a
          className="cell-hscroll"
          title={`查看 ${text || record.station_id} 站点下的设备`}
          onClick={(e) => {
            e.stopPropagation();
            setPage(1);
            setFilters((f) => ({ ...f, station_id: String(record.station_id) }));
          }}
        >
          {text || `站点#${record.station_id}`}
        </a>
      ),
    },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status]}>{statusTextMap[status] || status}</Tag>
      ),
    },
    { 
      title: t('pages.devices.health_score'), 
      dataIndex: 'health_score', 
      key: 'health_score', 
      width: 100,
      render: (score: number) => (
        <Badge 
          count={`${score || 0}%`} 
          style={{ 
            backgroundColor: score > 80 ? '#34a853' : score > 50 ? '#f5a623' : '#ea4335' 
          }} 
        />
      ),
    },
    {
      title: '利用率',
      key: 'utilization_rate',
      width: 100,
      render: (_: unknown, record: Device) => {
        const rate = record.utilization_rate ?? utilizationMap[record.id];
        if (rate == null) return <span style={{ color: '#999' }}>—</span>;
        const color = rate > 90 ? '#ff4d4f' : rate < 30 ? '#fa8c16' : '#52c41a';
        const bgColor = rate > 90 ? '#fff1f0' : rate < 30 ? '#fff7e6' : '#f6ffed';
        return (
          <Tooltip title={rate > 90 ? '过载' : rate < 30 ? '低利用率' : '正常'}>
            <Tag color={rate > 90 ? 'red' : rate < 30 ? 'orange' : 'green'}>
              {rate}%
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_: unknown, record: Device) => renderActions(record),
    },
  ];

  const hasDevices = devices.length > 0 || !loading;

  const retryFetch = () => {
    setPage(1);
    fetchDevices();
  };

  return (
    <PageWrapper
      loading={loading && devices.length === 0}
      skeletonType="table"
      skeletonCount={8}
      hasData={hasDevices}
      empty={{
        type: 'device',
        actionText: '添加设备',
        onAction: handleCreate,
      }}
      transition="slide-up"
    >
    <div className="page-container">
      <Card title={t('pages.devices.list')} extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={retryFetch}>{t('app.refresh')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('pages.devices.add')}
          </Button>
        </Space>
      }>
        <Row gutter={[8, 12]} justify="space-between" style={{ marginBottom: 16 }} className="filter-row">
          <Col xs={24} sm={12} md={6}>
            <Input
              placeholder={t('pages.devices.search_placeholder')}
              prefix={<SearchOutlined />}
              value={filters.search}
              onChange={(e) => setFilters({...filters, search: e.target.value})}
              onPressEnter={fetchDevices}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="所属站点"
              allowClear
              showSearch
              optionFilterProp="children"
              value={filters.station_id || undefined}
              onChange={(value) => { setPage(1); setFilters({ ...filters, station_id: value ? String(value) : '' }); }}
            >
              {stationOptions.map((s: any) => (
                <Option key={s.id} value={String(s.id)}>{s.name}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder={t('pages.devices.type')}
              allowClear
              value={filters.type}
              onChange={(value) => setFilters({...filters, type: value || ''})}
            >
              <Option value="CHARGER_DC">{t('pages.devices.type_charger_dc')}</Option>
              <Option value="CHARGER_AC">{t('pages.devices.type_charger_ac')}</Option>
              <Option value="PV_INVERTER">{t('pages.devices.type_pv_inverter')}</Option>
              <Option value="BATTERY_INVERTER">{t('pages.devices.type_battery_inverter')}</Option>
              <Option value="PCS">{t('pages.devices.type_pcs')}</Option>
              <Option value="BATTERY">{t('pages.devices.type_battery')}</Option>
              <Option value="METER">{t('pages.devices.type_meter')}</Option>
              <Option value="GATEWAY">{t('pages.devices.type_gateway')}</Option>
            </Select>
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder={t('pages.devices.status')}
              allowClear
              value={filters.status}
              onChange={(value) => setFilters({...filters, status: value || ''})}
            >
              <Option value="ONLINE">{t('pages.devices.status_online')}</Option>
              <Option value="OFFLINE">{t('pages.devices.status_offline')}</Option>
              <Option value="CHARGING">{t('pages.devices.status_charging')}</Option>
              <Option value="FAULT">{t('pages.devices.status_fault')}</Option>
              <Option value="MAINTENANCE">{t('pages.devices.status_maintenance')}</Option>
            </Select>
          </Col>
          <Col xs={24} sm={12} md={4}>
            <Button type="primary" onClick={fetchDevices} block>
              <FilterOutlined /> {t('app.filter')}
            </Button>
          </Col>
        </Row>

        {/* 列表：移动端卡片 / 桌面表格（横向滚动） */}
        {isMobile ? (
          loading ? (
            <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>
          ) : (
            <div>
              {devices.map(record => {
                const statusColor = statusColorMap[record.status];
                const statusText = statusTextMap[record.status] || record.status;
                const typeText = typeTextMap[record.type] || record.type;
                const rate = record.utilization_rate ?? utilizationMap[record.id];
                return (
                  <Card
                    key={record.id}
                    size="small"
                    data-testid="device-mobile-card"
                    style={{ marginBottom: 8 }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <Space>
                        <DesktopOutlined />
                        <strong>{record.name}</strong>
                      </Space>
                      <Tag color={statusColor}>{statusText}</Tag>
                    </div>
                    <Space size={4} wrap style={{ marginBottom: 6 }}>
                      <span style={{ color: '#999', fontSize: 12 }}>{record.sn}</span>
                      <Tag>{typeText}</Tag>
                      {record.model && <span style={{ color: '#999', fontSize: 12 }}>{record.model}</span>}
                    </Space>
                    <Space size={4} wrap style={{ marginBottom: 8 }}>
                      <Badge
                        count={`${record.health_score || 0}%`}
                        style={{ backgroundColor: record.health_score > 80 ? '#34a853' : record.health_score > 50 ? '#f5a623' : '#ea4335' }}
                      />
                      {rate != null && (
                        <Tag color={rate > 90 ? 'red' : rate < 30 ? 'orange' : 'green'}>{rate}%</Tag>
                      )}
                    </Space>
                    {renderActions(record)}
                  </Card>
                );
              })}
            </div>
          )
        ) : (
          <div className="table-scroll-x">
          <AutoHeightTable
            scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
            columns={columns}
            dataSource={devices}
            rowKey="id"
            loading={loading}
            pagination={{
              current: page,
              pageSize: pageSize,
              total: total,
              showSizeChanger: true,
              showTotal: (total) => t('app.total', { count: total }),
              onChange: (p, ps) => {
                if (ps !== pageSize) manualPageSize.current = true;
                setPage(p);
                setPageSize(ps);
              },
            }}
          />
          </div>
        )}
      </Card>

      {/* 设备详情 & 控制面板 */}
      <Modal
        title={`设备详情 - ${selectedDevice?.name || ''}`}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={isMobile ? modalFullWidth : 900}
      >
        {selectedDevice && (
          <>
            {/* SN编码与所属站点 (2026-10-09 丁哥: 展示在详情页, 不占列表) */}
            <Space size="middle" style={{ marginBottom: 12 }} wrap>
              <Tag color="blue">SN编码: {selectedDevice.sn || '-'}</Tag>
              <Tag color="geekblue">所属站点: {selectedDevice.station_name || `站点#${selectedDevice.station_id}`}</Tag>
              <Tag>设备编码: {selectedDevice.code || '-'}</Tag>
            </Space>
            {/* 上下文注入数据标记 */}
            <div
              data-context-json={JSON.stringify({
                device: {
                  id: selectedDevice.id,
                  name: selectedDevice.name,
                  sn: selectedDevice.sn,
                  code: selectedDevice.code,
                  type: selectedDevice.type,
                  model: selectedDevice.model,
                  manufacturer: selectedDevice.manufacturer,
                  status: selectedDevice.status,
                  health_score: selectedDevice.health_score,
                  station_id: selectedDevice.station_id,
                },
              })}
              data-device-id={String(selectedDevice.id)}
              data-device-name={selectedDevice.name || ''}
              data-device-sn={selectedDevice.sn || ''}
              data-device-type={selectedDevice.type || ''}
              data-device-status={selectedDevice.status || ''}
              data-device-health={String(selectedDevice.health_score || 0)}
              data-device-station={String(selectedDevice.station_id || 0)}
              style={{ display: 'none' }}
            />
            <DeviceEfficiencyDetail
              deviceId={selectedDevice.id}
              deviceType={selectedDevice.type}
            />
            <div style={{ marginTop: 16 }}>
              <DeviceControlPanel
                deviceId={selectedDevice.id}
                deviceName={selectedDevice.name}
                deviceType={selectedDevice.type}
                deviceStatus={selectedDevice.status}
              />
            </div>
          </>
        )}
      </Modal>

      {/* 参数配置弹窗 */}
      {selectedDevice && (
        <DeviceConfigPanel
          deviceId={selectedDevice.id}
          deviceName={selectedDevice.name}
          open={configVisible}
          onClose={() => setConfigVisible(false)}
        />
      )}

      {/* 固件升级弹窗 */}
      {selectedDevice && (
        <FirmwareUpgradeModal
          open={firmwareVisible}
          device={selectedDevice}
          onCancel={() => setFirmwareVisible(false)}
          onSuccess={() => { setFirmwareVisible(false); fetchDevices(); }}
        />
      )}

      {/* 新增/编辑弹窗 */}
      <Modal
        title={selectedDevice ? t('pages.devices.edit') : t('pages.devices.add')}
        open={modalVisible}
        onOk={handleSave}
        onCancel={() => setModalVisible(false)}
        width={isMobile ? modalFullWidth : 600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="sn" label={t('pages.devices.sn')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label={t('pages.devices.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label={t('pages.devices.code')} extra="留空自动生成（SN后12位）">
            <Input placeholder="平台自定义业务码，可留空" />
          </Form.Item>
          <Form.Item name="type" label={t('pages.devices.type')}>
            <Select>
              <Option value="CHARGER_DC">{t('pages.devices.type_charger_dc')}</Option>
              <Option value="CHARGER_AC">{t('pages.devices.type_charger_ac')}</Option>
              <Option value="PV_INVERTER">{t('pages.devices.type_pv_inverter')}</Option>
              <Option value="BATTERY_INVERTER">{t('pages.devices.type_battery_inverter')}</Option>
              <Option value="PCS">{t('pages.devices.type_pcs')}</Option>
              <Option value="BATTERY">{t('pages.devices.type_battery')}</Option>
              <Option value="METER">{t('pages.devices.type_meter')}</Option>
              <Option value="GATEWAY">{t('pages.devices.type_gateway')}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="manufacturer" label={t('pages.devices.manufacturer')}>
            <AutoComplete
              options={brandOptions.map((b: string) => ({ value: b }))}
              filterOption={(input, option) => (option?.value || '').toLowerCase().includes(input.toLowerCase())}
              onChange={(v) => setCurBrand(v || '')}
              placeholder="选择或输入新品牌（自动存入设备库）"
            />
          </Form.Item>
          <Form.Item name="model" label={t('pages.devices.model')}>
            <AutoComplete
              options={modelOptions.map((m: string) => ({ value: m }))}
              filterOption={(input, option) => (option?.value || '').toLowerCase().includes(input.toLowerCase())}
              placeholder="选择或输入新型号（自动存入设备库）"
            />
          </Form.Item>
          <Form.Item name="protocol_type" label="通讯协议">
            <Select allowClear placeholder="选择设备接入协议">
              {protocolOptions.map((p) => (
                <Option key={p} value={p}>{p}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="station_id" label={t('pages.devices.station')}>
            <Input type="number" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
    </PageWrapper>
  );
};

export default DeviceListPage;
