/**
 * 车队 - 费用结算页面
 *
 * 功能：账单列表 / 账单详情(明细) / 生成账单 / 确认/付款 / 发票管理
 * API: /api/v1/fleet/settlement/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Tabs, InputNumber, DatePicker, Drawer,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DollarOutlined,
  FileTextOutlined, CheckCircleOutlined, FileProtectOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 常量 ── */
const BILL_STATUS_COLORS: Record<string, string> = {
  pending: 'orange', confirmed: 'blue', paid: 'green', disputed: 'red',
};
const BILL_STATUS_TEXT: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', paid: '已付款', disputed: '有争议',
};
const INVOICE_STATUS_TEXT: Record<string, string> = {
  pending: '待开具', issued: '已开具', rejected: '已驳回',
};

/* ── 组件 ── */
const FleetSettlementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('bills');
  const [loading, setLoading] = useState(false);
  const [enterpriseId, setEnterpriseId] = useState<number | undefined>(undefined);

  // 账单
  const [bills, setBills] = useState<any[]>([]);
  const [billsTotal, setBillsTotal] = useState(0);
  const [billsPage, setBillsPage] = useState(1);
  const [generateModalOpen, setGenerateModalOpen] = useState(false);
  const [payModalOpen, setPayModalOpen] = useState(false);
  const [payingBill, setPayingBill] = useState<any>(null);
  const [payAmount, setPayAmount] = useState(0);
  const [generateForm] = Form.useForm();

  // 账单详情
  const [drawerBill, setDrawerBill] = useState<any>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [billDetails, setBillDetails] = useState<any[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);

  // 发票
  const [invoices, setInvoices] = useState<any[]>([]);
  const [invoicesTotal, setInvoicesTotal] = useState(0);
  const [invoicesPage, setInvoicesPage] = useState(1);
  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false);
  const [invoiceBillId, setInvoiceBillId] = useState<number | null>(null);
  const [invoiceForm] = Form.useForm();

  const loadBills = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/settlement/bills', {
        params: { enterprise_id: enterpriseId, page: billsPage, page_size: 10 },
      });
      setBills(data?.items || []);
      setBillsTotal(data?.total || 0);
    } catch { setBills([]); }
    finally { setLoading(false); }
  }, [enterpriseId, billsPage]);

  const loadInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/settlement/invoices', {
        params: { enterprise_id: enterpriseId, page: invoicesPage, page_size: 10 },
      });
      setInvoices(data?.items || []);
      setInvoicesTotal(data?.total || 0);
    } catch { setInvoices([]); }
    finally { setLoading(false); }
  }, [enterpriseId, invoicesPage]);

  useEffect(() => {
    if (activeTab === 'bills') loadBills();
    else if (activeTab === 'invoices') loadInvoices();
  }, [activeTab, loadBills, loadInvoices]);

  /* ── 账单操作 ── */
  const handleGenerate = async () => {
    try {
      const values = await generateForm.validateFields();
      const billPeriod = values.bill_period ? dayjs(values.bill_period).format('YYYY-MM') : undefined;
      if (!billPeriod) { message.error('请选择账期'); return; }
      await api.post('/fleet/settlement/bills/generate', {
        enterprise_id: values.enterprise_id,
        bill_period: billPeriod,
      });
      message.success('账单已生成');
      setGenerateModalOpen(false);
      generateForm.resetFields();
      loadBills();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('生成失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleConfirmBill = async (id: number) => {
    try {
      await api.post(`/fleet/settlement/bills/${id}/confirm`, {});
      message.success('账单已确认');
      loadBills();
    } catch (err: any) {
      message.error('确认失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handlePay = async () => {
    if (!payingBill || payAmount <= 0) return;
    try {
      await api.post(`/fleet/settlement/bills/${payingBill.id}/pay`, {
        paid_amount: payAmount,
      });
      message.success('付款成功');
      setPayModalOpen(false);
      setPayingBill(null);
      setPayAmount(0);
      loadBills();
    } catch (err: any) {
      message.error('付款失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openBillDetail = async (bill: any) => {
    setDrawerBill(bill);
    setDrawerOpen(true);
    setDetailsLoading(true);
    try {
      const { data } = await api.get(`/fleet/settlement/bills/${bill.id}/details`, {
        params: { page: 1, page_size: 20 },
      });
      setBillDetails(data?.items || []);
    } catch { setBillDetails([]); }
    finally { setDetailsLoading(false); }
  };

  const handleRequestInvoice = async () => {
    if (!invoiceBillId) return;
    try {
      const values = await invoiceForm.validateFields();
      await api.post(`/fleet/settlement/bills/${invoiceBillId}/invoice`, values);
      message.success('发票申请已提交');
      setInvoiceModalOpen(false);
      invoiceForm.resetFields();
      setInvoiceBillId(null);
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('申请失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const refreshTab = () => {
    if (activeTab === 'bills') loadBills();
    else loadInvoices();
  };

  /* ── 统计 ── */
  const billsStats = {
    total: bills.length,
    pending: bills.filter(b => b.status === 'pending').length,
    paid: bills.filter(b => b.status === 'paid').length,
    totalAmount: bills.reduce((s, b) => s + (b.total_amount || 0), 0),
  };

  const billColumns = [
    { title: '账单编号', dataIndex: 'bill_no', key: 'bill_no', width: 180, render: (v: string, r: any) => <a onClick={() => openBillDetail(r)}>{v}</a> },
    { title: '账期', dataIndex: 'bill_period', key: 'bill_period', width: 90 },
    { title: '订单数', dataIndex: 'total_orders', key: 'total_orders', width: 70, align: 'right' as const },
    { title: '电量(kWh)', dataIndex: 'total_energy_kwh', key: 'total_energy_kwh', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '总金额(¥)', dataIndex: 'total_amount', key: 'total_amount', width: 120, align: 'right' as const, render: (v: number) => <span style={{ fontWeight: 600 }}>{v?.toFixed(2) || '0.00'}</span> },
    { title: '已付(¥)', dataIndex: 'paid_amount', key: 'paid_amount', width: 110, align: 'right' as const, render: (v: number) => <span style={{ color: '#52c41a' }}>{v?.toFixed(2) || '0.00'}</span> },
    { title: '待付(¥)', dataIndex: 'balance_amount', key: 'balance_amount', width: 110, align: 'right' as const, render: (v: number) => v > 0 ? <span style={{ color: '#fa541c' }}>{v.toFixed(2)}</span> : <span>0.00</span> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={BILL_STATUS_COLORS[v] || 'default'}>{BILL_STATUS_TEXT[v] || v}</Tag> },
    {
      title: '操作', key: 'action', width: 220,
      render: (_: unknown, r: any) => (
        <Space wrap>
          {r.status === 'pending' && (
            <Popconfirm title="确认此账单？" onConfirm={() => handleConfirmBill(r.id)}>
              <Button size="small" type="link" icon={<CheckCircleOutlined />}>确认</Button>
            </Popconfirm>
          )}
          {r.status === 'confirmed' && (
            <Button size="small" type="link" icon={<DollarOutlined />} onClick={() => { setPayingBill(r); setPayAmount(r.balance_amount || r.total_amount || 0); setPayModalOpen(true); }}>付款</Button>
          )}
          <Button size="small" type="link" icon={<FileProtectOutlined />} onClick={() => { setInvoiceBillId(r.id); invoiceForm.resetFields(); invoiceForm.setFieldsValue({ invoice_type: 'general' }); setInvoiceModalOpen(true); }}>发票</Button>
        </Space>
      ),
    },
  ];

  const invoiceColumns = [
    { title: '账单ID', dataIndex: 'bill_id', key: 'bill_id', width: 80 },
    { title: '企业ID', dataIndex: 'enterprise_id', key: 'enterprise_id', width: 80 },
    { title: '金额(¥)', dataIndex: 'amount', key: 'amount', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '发票类型', dataIndex: 'invoice_type', key: 'invoice_type', width: 90, render: (v: string) => <Tag>{v === 'special' ? '专票' : '普票'}</Tag> },
    { title: '抬头', dataIndex: 'title', key: 'title', width: 200, ellipsis: true },
    { title: '税号', dataIndex: 'tax_no', key: 'tax_no', width: 140, render: (v: string) => v || '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={v === 'issued' ? 'green' : v === 'rejected' ? 'red' : 'orange'}>{INVOICE_STATUS_TEXT[v] || v}</Tag> },
  ];

  return (
    <PageWrapper loading={loading} skeletonType="table" hasData={true} transition="slide-up">
      <div className="page-container">
        {activeTab === 'bills' && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}><Card><Statistic title="账单总数" value={billsStats.total} prefix={<FileTextOutlined />} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="待确认" value={billsStats.pending} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="已付款" value={billsStats.paid} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="总金额(¥)" value={billsStats.totalAmount} precision={2} prefix={<DollarOutlined />} /></Card></Col>
          </Row>
        )}

        <Card extra={
          <Space>
            <InputNumber placeholder="企业ID" value={enterpriseId} min={1} onChange={v => setEnterpriseId(v || undefined)} style={{ width: 100 }} />
            <Button icon={<ReloadOutlined />} onClick={refreshTab}>刷新</Button>
            {activeTab === 'bills' && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { generateForm.resetFields(); setGenerateModalOpen(true); }}>生成账单</Button>
            )}
          </Space>
        }>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
            { key: 'bills', label: <span><FileTextOutlined /> 对账账单</span>, children: (
              <Table columns={billColumns} dataSource={bills} rowKey="id" loading={loading}
                pagination={{ current: billsPage, pageSize: 10, total: billsTotal, onChange: setBillsPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'invoices', label: <span><FileProtectOutlined /> 发票管理</span>, children: (
              <Table columns={invoiceColumns} dataSource={invoices} rowKey="id" loading={loading}
                pagination={{ current: invoicesPage, pageSize: 10, total: invoicesTotal, onChange: setInvoicesPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
          ]} />
        </Card>

        {/* 生成账单 Modal */}
        <Modal title="生成对账账单" open={generateModalOpen} onOk={handleGenerate}
          onCancel={() => { setGenerateModalOpen(false); generateForm.resetFields(); }}
          width={420} destroyOnHidden
        >
          <Form form={generateForm} layout="vertical">
            <Form.Item name="enterprise_id" label="企业ID" rules={[{ required: true, message: '请输入企业ID' }]}>
              <InputNumber style={{ width: '100%' }} min={1} />
            </Form.Item>
            <Form.Item name="bill_period" label="账期(月份)" rules={[{ required: true, message: '请选择账期' }]}>
              <DatePicker picker="month" style={{ width: '100%' }} placeholder="选择账期月份" />
            </Form.Item>
          </Form>
        </Modal>

        {/* 付款 Modal */}
        <Modal title={`付款 - ${payingBill?.bill_no || ''}`} open={payModalOpen} onOk={handlePay}
          onCancel={() => { setPayModalOpen(false); setPayingBill(null); setPayAmount(0); }}
        >
          <Form layout="vertical">
            <Form.Item label="应付金额(¥)">
              <InputNumber style={{ width: '100%' }} value={payAmount} min={0.01} step={100} precision={2}
                onChange={v => setPayAmount(v || 0)} prefix="¥"
              />
            </Form.Item>
          </Form>
        </Modal>

        {/* 发票申请 Modal */}
        <Modal title="申请发票" open={invoiceModalOpen} onOk={handleRequestInvoice}
          onCancel={() => { setInvoiceModalOpen(false); invoiceForm.resetFields(); setInvoiceBillId(null); }}
          width={480} destroyOnHidden
        >
          <Form form={invoiceForm} layout="vertical">
            <Form.Item name="title" label="发票抬头" rules={[{ required: true, message: '请输入抬头' }]}>
              <Input placeholder="企业全称" />
            </Form.Item>
            <Form.Item name="tax_no" label="税号">
              <Input placeholder="纳税人识别号" />
            </Form.Item>
            <Form.Item name="invoice_type" label="发票类型" initialValue="general">
              <Select>
                <Select.Option value="general">普通发票</Select.Option>
                <Select.Option value="special">增值税专用发票</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="email" label="接收邮箱">
              <Input placeholder="email@example.com" />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={2} />
            </Form.Item>
          </Form>
        </Modal>

        {/* 账单详情抽屉 */}
        <Drawer title={`账单详情 - ${drawerBill?.bill_no || ''}`} open={drawerOpen} width={720}
          onClose={() => { setDrawerOpen(false); setDrawerBill(null); }}
        >
          {drawerBill && (
            <>
              <Row gutter={16}>
                <Col span={6}><Statistic title="账期" value={drawerBill.bill_period} /></Col>
                <Col span={6}><Statistic title="订单数" value={drawerBill.total_orders} /></Col>
                <Col span={6}><Statistic title="总金额" value={drawerBill.total_amount} precision={2} prefix="¥" /></Col>
                <Col span={6}><Statistic title="状态" value={BILL_STATUS_TEXT[drawerBill.status] || drawerBill.status} /></Col>
              </Row>
              <Card title="费用明细" size="small" style={{ marginTop: 16 }} loading={detailsLoading}>
                <Table dataSource={billDetails} rowKey="id" size="small" pagination={{ pageSize: 10 }}
                  columns={[
                    { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 150, ellipsis: true },
                    { title: '车牌', dataIndex: 'plate_number', key: 'plate_number', width: 100 },
                    { title: '电量(kWh)', dataIndex: 'energy_kwh', key: 'energy_kwh', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
                    { title: '电费', dataIndex: 'charge_fee', key: 'charge_fee', width: 80, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
                    { title: '服务费', dataIndex: 'service_fee', key: 'service_fee', width: 80, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
                    { title: '停车费', dataIndex: 'parking_fee', key: 'parking_fee', width: 80, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
                    { title: '总额', dataIndex: 'total_amount', key: 'total_amount', width: 90, align: 'right' as const, render: (v: number) => <span style={{ fontWeight: 600 }}>{v?.toFixed(2) || '0.00'}</span> },
                  ]}
                />
              </Card>
            </>
          )}
        </Drawer>
      </div>
    </PageWrapper>
  );
};

export default FleetSettlementPage;
