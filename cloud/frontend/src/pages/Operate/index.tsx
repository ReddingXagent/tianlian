/**
 * 天链 V3 - 运营管理页面
 *
 * Tab 整合:
 *   运营首页(Dashboard) / 订单管理 / 退款管理 / 结算对账 / 发票管理
 *   定价管理 / 运营分析 / 用户管理 / 折扣管理 / 优惠券 / 积分
 *
 * 路由: /operate(默认运营首页) 与 /operate/:tab 深度链接联动 activeTab
 */
import React, { useState, useEffect, Suspense } from 'react';
import { lazyRetry } from '../../utils/lazyRetry';
import { Card, Tabs, Spin } from 'antd';
import {
  DashboardOutlined, DollarOutlined, ReloadOutlined, CheckCircleOutlined,
  LineChartOutlined, UserOutlined, GiftOutlined, GoldOutlined,
  ApiOutlined, SafetyCertificateOutlined, QrcodeOutlined,
  EnvironmentOutlined, DesktopOutlined,
  CarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import PageWrapper from '../../components/PageWrapper';
import OrdersIndex from './Orders';
import RefundsIndex from './Refunds';
import SettlementIndex from './Settlement';
import InvoicesIndex from './Invoices';

// 懒加载: 定价/分析/看板 + 4个原独立页面
const PricingPage = lazyRetry(() => import('./Pricing'));
const AnalyticsPage = lazyRetry(() => import('./Analytics'));
const DashboardPage = lazyRetry(() => import('./Dashboard'));
// 互联互通 / 市政监管 (迁移自 admin, 按团队隔离)
const InterconnectPage = lazyRetry(() => import('./Interconnect'));
const SupervisionPage = lazyRetry(() => import('./Supervision'));
// 充电桩收费二维码
const QRCodesPage = lazyRetry(() => import('./QRCodes'));
const UserTypeManagement = lazyRetry(() => import('../UserTypeManagement'));
const DiscountManagement = lazyRetry(() => import('../DiscountManagement'));
const CouponManagement = lazyRetry(() => import('../CouponManagement'));
const PointsManagement = lazyRetry(() => import('../PointsManagement'));
// 站点管理 / 设备管理 (建站/加设备自助入口, 后端已对齐非admin权限)
const StationsPage = lazyRetry(() => import('../Stations'));
const DevicesPage = lazyRetry(() => import('../Devices'));
// 车队管理 (Enterprise 实体 CRUD)
const FleetManagement = lazyRetry(() => import('./Fleet'));
import RechargeApprovalPage from './RechargeApproval';
const V2GOperationsPage = lazyRetry(() => import('./V2GOperations'));

const LazyFallback = () => (
  <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
);

const VALID_TABS = [
  'dashboard', 'orders', 'refunds', 'settlement', 'invoices',
  'pricing', 'analytics', 'users', 'discounts', 'coupons', 'points',
  'interconnect', 'supervision', 'qrcodes',
  'stations', 'devices',
  'fleet',
  'recharge-approval',
  'v2g',
];

/* ── 组件 ── */
const OperatePage: React.FC = () => {
  const { tab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>(
    tab && VALID_TABS.includes(tab) ? tab : 'dashboard',
  );

  // URL 参数 → activeTab 单向同步: 左侧菜单 navigate('/operate/<tab>') 复用同一组件实例,
  // 仅靠 useState 初始值会导致后续菜单点击 URL 变了但内容不切换("点击没反应")
  useEffect(() => {
    const next = tab && VALID_TABS.includes(tab) ? tab : 'dashboard';
    setActiveTab(prev => (prev === next ? prev : next));
  }, [tab]);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    navigate(`/operate/${key}`);
  };

  const tabItems = [
    {
      key: 'dashboard',
      label: <span><DashboardOutlined /> 运营首页</span>,
      children: <Suspense fallback={<LazyFallback />}><DashboardPage /></Suspense>,
    },
    {
      key: 'orders',
      label: <span><DollarOutlined /> 订单管理</span>,
      children: <Card><OrdersIndex /></Card>,
    },
    {
      key: 'refunds',
      label: <span><ReloadOutlined /> 退款管理</span>,
      children: <Card><RefundsIndex /></Card>,
    },
    {
      key: 'settlement',
      label: <span><CheckCircleOutlined /> 结算对账</span>,
      children: <Card><SettlementIndex /></Card>,
    },
    {
      key: 'invoices',
      label: <span><DollarOutlined /> 发票管理</span>,
      children: <Card><InvoicesIndex /></Card>,
    },
    {
      key: 'pricing',
      label: <span><DollarOutlined /> 定价管理</span>,
      children: <Suspense fallback={<LazyFallback />}><Card><PricingPage /></Card></Suspense>,
    },
    {
      key: 'analytics',
      label: <span><LineChartOutlined /> 运营分析</span>,
      children: <Suspense fallback={<LazyFallback />}><Card><AnalyticsPage /></Card></Suspense>,
    },
    {
      key: 'users',
      label: <span><UserOutlined /> 用户管理</span>,
      children: <Suspense fallback={<LazyFallback />}><UserTypeManagement /></Suspense>,
    },
    {
      key: 'discounts',
      label: <span><DollarOutlined /> 折扣管理</span>,
      children: <Suspense fallback={<LazyFallback />}><DiscountManagement /></Suspense>,
    },
    {
      key: 'coupons',
      label: <span><GiftOutlined /> 优惠券</span>,
      children: <Suspense fallback={<LazyFallback />}><CouponManagement /></Suspense>,
    },
    {
      key: 'points',
      label: <span><GoldOutlined /> 积分</span>,
      children: <Suspense fallback={<LazyFallback />}><PointsManagement /></Suspense>,
    },
    {
      key: 'interconnect',
      label: <span><ApiOutlined /> 互联互通</span>,
      children: <Suspense fallback={<LazyFallback />}><InterconnectPage /></Suspense>,
    },
    {
      key: 'supervision',
      label: <span><SafetyCertificateOutlined /> 市政监管</span>,
      children: <Suspense fallback={<LazyFallback />}><SupervisionPage /></Suspense>,
    },
    {
      key: 'qrcodes',
      label: <span><QrcodeOutlined /> 二维码管理</span>,
      children: <Suspense fallback={<LazyFallback />}><Card><QRCodesPage /></Card></Suspense>,
    },
    {
      key: 'stations',
      label: <span><EnvironmentOutlined /> 站点管理</span>,
      children: <Suspense fallback={<LazyFallback />}><StationsPage /></Suspense>,
    },
    {
      key: 'devices',
      label: <span><DesktopOutlined /> 设备管理</span>,
      children: <Suspense fallback={<LazyFallback />}><DevicesPage /></Suspense>,
    },
    {
      key: 'fleet',
      label: <span><CarOutlined /> 车队管理</span>,
      children: <Suspense fallback={<LazyFallback />}><FleetManagement /></Suspense>,
    },
    {
      key: 'recharge-approval',
      label: <span><DollarOutlined /> 充值审核</span>,
      children: <RechargeApprovalPage />,
    },
    {
      key: 'v2g',
      label: <span><ThunderboltOutlined /> V2G运营</span>,
      children: <Suspense fallback={<LazyFallback />}><V2GOperationsPage /></Suspense>,
    },
  ];

  return (
    <PageWrapper hasData transition="slide-up">
      <div className="page-container">
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={tabItems}
        />
      </div>
    </PageWrapper>
  );
};

export default OperatePage;
