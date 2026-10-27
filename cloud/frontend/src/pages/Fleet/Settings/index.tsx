/**
 * 车队 - 设置页面
 *
 * 两个 Tab：
 *   1. 企业信息    —— 对接 GET/PUT /api/v1/enterprises/{id}（字段 name/code/contact/phone/status）
 *   2. 车辆默认配置 —— 本地 localStorage 持久化（后端 Enterprise 模型无对应字段）
 *
 * 字段契约对齐后端 app/api/v1/enterprises.py：
 *   - 联系人/电话字段为 contact / phone（非 contact_person / contact_phone）
 *   - address / description 后端不支持，仅本地保存
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Form, Input, Button, Select, Tabs, InputNumber, Space, message, Row, Col, Spin, Tag, Table,
} from 'antd';
import {
  SettingOutlined, SaveOutlined, BankOutlined, CarOutlined, ReloadOutlined, EnvironmentOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface Enterprise {
  id: number;
  name: string;
  code: string;
  contact?: string;
  phone?: string;
  balance?: number;
  credit_limit?: number;
  status: string;
  owner_team_id?: number;
}

interface StationItem {
  id: number;
  name: string;
  code: string;
  address?: string;
  status?: string;
  team_id?: number;
}

interface VehicleDefaults {
  inspection_period_months: number;
  insurance_reminder_days: number;
  maintenance_interval_km: number;
}

/* ── 常量 ── */
const DEFAULT_VEHICLE: VehicleDefaults = {
  inspection_period_months: 12,
  insurance_reminder_days: 30,
  maintenance_interval_km: 10000,
};

const vehicleStorageKey = (eid: number) => `fleet:settings:vehicle:${eid}`;
const addressStorageKey = (eid: number) => `fleet:settings:addr:${eid}`;
const descStorageKey = (eid: number) => `fleet:settings:desc:${eid}`;

/* ── 组件 ── */
const FleetSettingsPage: React.FC = () => {
  const [enterprises, setEnterprises] = useState<Enterprise[]>([]);
  const [enterpriseId, setEnterpriseId] = useState<number | undefined>();
  const [listLoading, setListLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [savingInfo, setSavingInfo] = useState(false);
  const [savingVehicle, setSavingVehicle] = useState(false);
  const [activeTab, setActiveTab] = useState('info');
  const [infoForm] = Form.useForm();
  const [vehicleForm] = Form.useForm();
  const [teams, setTeams] = useState<{id:number;name:string}[]>([]);
  const [boundStations, setBoundStations] = useState<StationItem[]>([]);

  /* ── 加载企业列表 ── */
  const loadList = useCallback(async () => {
    setListLoading(true);
    try {
      const { data: body } = await api.get('/enterprises');
      const items: Enterprise[] = body?.data?.items || body?.items || [];
      setEnterprises(items);
      if (items.length) setEnterpriseId(items[0].id);
    } catch {
      setEnterprises([]);
    } finally {
      setListLoading(false);
    }
  }, []);

  /* ── 加载企业详情 + 本地配置 ── */
  const loadDetail = useCallback(async (eid: number) => {
    setDetailLoading(true);
    try {
      const { data: body } = await api.get(`/enterprises/${eid}`);
      const ent = body?.data || body || {};
      infoForm.setFieldsValue({
        name: ent.name,
        code: ent.code,
        contact: ent.contact,
        phone: ent.phone,
        status: ent.status || 'active',
        owner_team_id: ent.owner_team_id,
        address: localStorage.getItem(addressStorageKey(eid)) || '',
        description: localStorage.getItem(descStorageKey(eid)) || '',
      });

      // 加载场站绑定（卡691532f2：只读展示，绑定操作已迁至运维侧 /operate/fleet）
      try {
        const boundRes = await api.get(`/enterprises/${eid}/stations`);
        setBoundStations(boundRes.data?.data || []);
      } catch {
        setBoundStations([]);
      }
      const raw = localStorage.getItem(vehicleStorageKey(eid));
      const vconf = raw ? { ...DEFAULT_VEHICLE, ...JSON.parse(raw) } : DEFAULT_VEHICLE;
      vehicleForm.setFieldsValue(vconf);
    } catch (err: any) {
      message.error('加载企业信息失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setDetailLoading(false);
    }
  }, [infoForm, vehicleForm]);

  /* ── 加载团队列表 ── */
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/teams');
        const items = data?.data?.items || data?.data || data?.items || [];
        setTeams(Array.isArray(items) ? items.map((t:any) => ({ id: t.id, name: t.name })) : []);
      } catch {
        // 静默处理：团队列表加载失败保留空列表
      }
    })();
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (enterpriseId) loadDetail(enterpriseId); }, [enterpriseId, loadDetail]);

  /* ── 保存企业信息（仅后端支持字段走 PUT；address/description 本地持久化） ── */
  const handleSaveInfo = async () => {
    if (!enterpriseId) return;
    try {
      const values = await infoForm.validateFields();
      setSavingInfo(true);
      await api.put(`/enterprises/${enterpriseId}`, {
        name: values.name,
        code: values.code,
        contact: values.contact,
        phone: values.phone,
        status: values.status,
        owner_team_id: values.owner_team_id,
      });
      localStorage.setItem(addressStorageKey(enterpriseId), values.address || '');
      localStorage.setItem(descStorageKey(enterpriseId), values.description || '');
      message.success('企业信息已保存');
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验失败，不报错
      message.error('保存失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSavingInfo(false);
    }
  };

  /* ── 保存车辆默认配置（本地持久化） ── */
  const handleSaveVehicle = async () => {
    if (!enterpriseId) return;
    try {
      const values = await vehicleForm.validateFields();
      setSavingVehicle(true);
      localStorage.setItem(vehicleStorageKey(enterpriseId), JSON.stringify(values));
      message.success('车辆配置已保存');
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('保存失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSavingVehicle(false);
    }
  };

  return (
    <PageWrapper loading={listLoading && enterprises.length === 0} hasData transition="slide-up">
      <div className="page-container">
        <Card
          title={<span><SettingOutlined /> 车队设置</span>}
          extra={
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
              <Button icon={<ReloadOutlined />} onClick={() => (enterpriseId ? loadDetail(enterpriseId) : loadList())}>
                刷新
              </Button>
            </Space>
          }
        >
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'info',
                label: <span><BankOutlined /> 企业信息</span>,
                children: (
                  <Spin spinning={detailLoading}>
                    <Form form={infoForm} layout="vertical" style={{ maxWidth: 720 }}>
                      <Row gutter={16}>
                        <Col span={12}>
                          <Form.Item name="name" label="企业名称" rules={[{ required: true, message: '请输入企业名称' }]}>
                            <Input placeholder="请输入企业名称" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item name="code" label="企业编码" rules={[{ required: true, message: '请输入企业编码' }]}>
                            <Input placeholder="如 TL-FLEET-001" />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Row gutter={16}>
                        <Col span={12}>
                          <Form.Item name="contact" label="联系人">
                            <Input placeholder="请输入联系人" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item name="phone" label="联系电话">
                            <Input placeholder="请输入联系电话" />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item name="status" label="状态">
                        <Select>
                          <Select.Option value="active">启用</Select.Option>
                          <Select.Option value="inactive">停用</Select.Option>
                          <Select.Option value="suspended">暂停</Select.Option>
                        </Select>
                      </Form.Item>
                      <Form.Item name="owner_team_id" label="经营团队">
                        <Select allowClear placeholder="选择经营团队" options={teams.map(t => ({ value: t.id, label: t.name }))} />
                      </Form.Item>
                      <Form.Item
                        name="address"
                        label={<span>地址 <Tag color="blue" style={{ marginLeft: 4 }}>本地保存</Tag></span>}
                      >
                        <Input placeholder="请输入地址（本地保存，不同步至服务端）" />
                      </Form.Item>
                      <Form.Item
                        name="description"
                        label={<span>描述 <Tag color="blue" style={{ marginLeft: 4 }}>本地保存</Tag></span>}
                      >
                        <Input.TextArea rows={3} placeholder="请输入描述（本地保存）" />
                      </Form.Item>
                      <Button type="primary" icon={<SaveOutlined />} loading={savingInfo} onClick={handleSaveInfo}>
                        保存企业信息
                      </Button>
                    </Form>
                  </Spin>
                ),
              },
              {
                key: 'stations',
                label: <span><EnvironmentOutlined /> 场站绑定</span>,
                forceRender: true,
                children: (
                  <Spin spinning={detailLoading}>
                    <div style={{ maxWidth: 720 }}>
                      <div style={{ marginBottom: 16, color: '#888' }}>
                        绑定由运营商在运维侧（车队管理）操作，此处仅展示当前绑定结果。
                      </div>
                      <Table
                        size="small"
                        dataSource={boundStations}
                        rowKey="id"
                        pagination={false}
                        columns={[
                          { title: '场站名称', dataIndex: 'name', key: 'name' },
                          { title: '编码', dataIndex: 'code', key: 'code' },
                          { title: '地址', dataIndex: 'address', key: 'address', ellipsis: true },
                          {
                            title: '状态', dataIndex: 'status', key: 'status',
                            render: (v: string) => v === 'normal' ? <Tag color="green">正常</Tag> : <Tag color="orange">{v}</Tag>,
                          },
                        ]}
                      />
                    </div>
                  </Spin>
                ),
              },
              {
                key: 'vehicle',
                label: <span><CarOutlined /> 车辆默认配置</span>,
                forceRender: true,
                children: (
                  <Spin spinning={detailLoading}>
                    <Form form={vehicleForm} layout="vertical" style={{ maxWidth: 720 }} initialValues={DEFAULT_VEHICLE}>
                      <Form.Item
                        name="inspection_period_months"
                        label="默认年检周期(月)"
                        rules={[{ required: true, message: '请输入年检周期' }]}
                      >
                        <InputNumber style={{ width: '100%' }} min={1} max={36} placeholder="如 12" />
                      </Form.Item>
                      <Form.Item
                        name="insurance_reminder_days"
                        label="保险提醒天数"
                        rules={[{ required: true, message: '请输入提醒天数' }]}
                      >
                        <InputNumber style={{ width: '100%' }} min={0} max={365} placeholder="如 30" />
                      </Form.Item>
                      <Form.Item
                        name="maintenance_interval_km"
                        label="里程保养间隔(km)"
                        rules={[{ required: true, message: '请输入保养间隔' }]}
                      >
                        <InputNumber style={{ width: '100%' }} min={100} step={1000} placeholder="如 10000" />
                      </Form.Item>
                      <Button type="primary" icon={<SaveOutlined />} loading={savingVehicle} onClick={handleSaveVehicle}>
                        保存车辆配置
                      </Button>
                    </Form>
                  </Spin>
                ),
              },
            ]}
          />
        </Card>
      </div>
    </PageWrapper>
  );
};

export default FleetSettingsPage;
