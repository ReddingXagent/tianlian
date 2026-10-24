import { Suspense } from 'react';
import { lazyRetry } from './utils/lazyRetry';
import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/Layout/AdminLayout';
import OfflineNotice from './components/OfflineNotice';
import ErrorBoundary from './components/ErrorBoundary';
import RouteGuard from './components/RouteGuard';
import PageTransition from './components/PageTransition';
import { getUserType } from './utils/auth';

// Phase48 - 数据大屏独立展示模式
const LargeScreen = lazyRetry(() => import('./pages/LargeScreen'));

// V2G设备管理
const V2GManagement = lazyRetry(() => import('./pages/Devices/V2GManagement'));
const V2GDeviceDetail = lazyRetry(() => import('./pages/Devices/V2GManagement/V2GDeviceDetail'));

// Loading fallback with spinner
const PageLoader = () => (
  <div style={{ display:'flex', justifyContent:'center', alignItems:'center', height:'100vh', background:'var(--bg-layout)' }}>
    <div style={{ textAlign: 'center' }}>
      <div
        style={{
          width: 40, height: 40, borderRadius: '50%',
          border: '3px solid var(--border-color)',
          borderTopColor: 'var(--primary-color)',
          animation: 'spin 0.8s linear infinite',
          margin: '0 auto 12px',
        }}
      />
      <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>加载中...</div>
    </div>
  </div>
);

// Lazy-loaded pages
const LoginPage = lazyRetry(() => import('./pages/Login'));
const RegisterPage = lazyRetry(() => import('./pages/Register'));
const Dashboard = lazyRetry(() => import('./pages/Dashboard'));
const Devices = lazyRetry(() => import('./pages/Devices'));
const Stations = lazyRetry(() => import('./pages/Stations'));
const WorkOrders = lazyRetry(() => import('./pages/WorkOrders'));
const WorkOrderStats = lazyRetry(() => import('./pages/WorkOrderStats'));
const Alarms = lazyRetry(() => import('./pages/Alarms'));
const Knowledge = lazyRetry(() => import('./pages/Knowledge'));
const KnowledgeDetail = lazyRetry(() => import('./pages/Knowledge/Detail'));
const KnowledgeEdit = lazyRetry(() => import('./pages/Knowledge/Edit'));
const Reports = lazyRetry(() => import('./pages/Reports'));
const ReportMgmt = lazyRetry(() => import('./pages/ReportMgmt'));
const Teams = lazyRetry(() => import('./pages/Teams'));
const Engineers = lazyRetry(() => import('./pages/Teams/Engineers'));
const TeamsRoles = lazyRetry(() => import('./pages/Teams/Roles'));
const Users = lazyRetry(() => import('./pages/Users'));
const Config = lazyRetry(() => import('./pages/Config'));
const Health = lazyRetry(() => import('./pages/Health'));
const Security = lazyRetry(() => import('./pages/Security'));
const Rbac = lazyRetry(() => import('./pages/Rbac'));
const ScanPage = lazyRetry(() => import('./pages/Scan'));
const InspectionOps = lazyRetry(() => import('./pages/InspectionOps'));
const TelemetryPage = lazyRetry(() => import('./pages/Telemetry'));
const TelemetryClassicPage = lazyRetry(() => import('./pages/TelemetryClassic'));
const FaultDiagnosisPage = lazyRetry(() => import('./pages/FaultDiagnosis'));
const AuditLogPage = lazyRetry(() => import('./pages/AuditLog'));
const OnCallPage = lazyRetry(() => import('./pages/OnCall'));
const RunbookPage = lazyRetry(() => import('./pages/Runbook'));
const HealingPage = lazyRetry(() => import('./pages/Healing'));
const SmartDiagnosisPage = lazyRetry(() => import('./pages/SmartDiagnosis'));
const EnergyReportPage = lazyRetry(() => import('./pages/EnergyReport'));
const DigitalTwinPage = lazyRetry(() => import('./pages/DigitalTwin'));
const VPPPage = lazyRetry(() => import('./pages/VPP'));
const PredictiveMaintenancePage = lazyRetry(() => import('./pages/PredictiveMaintenance'));
const OpsDashboardPage = lazyRetry(() => import('./pages/OpsDashboard'));
// 经营驾驶舱 (拥有者视角: 收入/利用率/毛利/ROI)
const OwnerCockpitPage = lazyRetry(() => import('./pages/OwnerCockpit'));

// Phase4 补缺页面
const ApiKeyPage = lazyRetry(() => import('./pages/ApiKey'));
const LogAnalysisPage = lazyRetry(() => import('./pages/LogAnalysis'));
const NotificationRulesPage = lazyRetry(() => import('./pages/NotificationRules'));
const MessageCenterPage = lazyRetry(() => import('./pages/MessageCenter'));
const RunbookApprovalPage = lazyRetry(() => import('./pages/RunbookApproval'));
const SSLCertificatesPage = lazyRetry(() => import('./pages/SSLCertificates'));
const WebhooksPage = lazyRetry(() => import('./pages/Webhooks'));

// Phase 4 - AI运维分析仪表板
const AnalyticsDashboardPage = lazyRetry(() => import('./pages/AnalyticsDashboard'));

// 效率分析报表子页面
const UtilizationAnalysis = lazyRetry(() => import('./pages/Reports/UtilizationAnalysis'));
const ChargeEfficiencyAnalysis = lazyRetry(() => import('./pages/Reports/ChargeEfficiencyAnalysis'));
const GenerationEfficiencyAnalysis = lazyRetry(() => import('./pages/Reports/GenerationEfficiencyAnalysis'));

// 运营管理 + 车队管理
const Operate = lazyRetry(() => import('./pages/Operate'));
const Fleet = lazyRetry(() => import('./pages/Fleet'));

// 天链助手 - AI对话浮窗
const ChatPanel = lazyRetry(() => import('./components/ChatPanel'));

// AI模型配置
const AIModelConfigPage = lazyRetry(() => import('./pages/AIModelConfig'));

// 数据管理（导出/备份/忘记密码处理，卡 922b2fba）
const DataOpsPage = lazyRetry(() => import('./pages/DataOps'));

// 平台管理页面
const PlatformDashboard = lazyRetry(() => import('./pages/PlatformDashboard'));
const GatewayPage = lazyRetry(() => import('./pages/Gateways'));
const LinksPage = lazyRetry(() => import('./pages/Links'));
const CloudPage = lazyRetry(() => import('./pages/Cloud'));
const TerminalsPage = lazyRetry(() => import('./pages/Terminals'));
const EdgeGatewaysPage = lazyRetry(() => import('./pages/Admin/EdgeGateways'));
const DeviceLibraryPage = lazyRetry(() => import('./pages/DeviceLibrary'));
const TenantsPage = lazyRetry(() => import('./pages/Tenants'));
const DeviceProtocolsPage = lazyRetry(() => import('./pages/DeviceProtocols'));
const ProtocolsPage = lazyRetry(() => import('./pages/Protocols'));

function App() {
  return (
    <>
    <ErrorBoundary>
    <OfflineNotice />
    <Suspense fallback={<PageLoader />}>
    <Routes>
      {/* 公共路由 - 无需守卫 */}
      <Route path="/login" element={<PageTransition effect="fade"><LoginPage /></PageTransition>} />
      <Route path="/register" element={<PageTransition effect="fade"><RegisterPage /></PageTransition>} />
      <Route path="/scan" element={<PageTransition effect="fade"><ScanPage /></PageTransition>} />
      {/* Phase48: 数据大屏独立展示模式 */}
      <Route path="/large-screen" element={
        <Suspense fallback={
          <div style={{ display:'flex', justifyContent:'center', alignItems:'center', height:'100vh', background:'#0a1628', color:'#e6f7ff' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ width:40, height:40, borderRadius:'50%', border:'3px solid rgba(24,144,255,0.3)', borderTopColor:'#1890ff', animation:'spin 0.8s linear infinite', margin:'0 auto 12px' }} />
              <div style={{ fontSize:14 }}>加载大屏...</div>
            </div>
          </div>
        }>
          <LargeScreen />
        </Suspense>
      } />

      {/* ======== 运维管理路由 (engineer/operator/fleet 可访问) ======== */}
      <Route path="/" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin", "engineer", "operator", "fleet"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="devices" element={<Devices />} />
        <Route path="devices/v2g" element={<V2GManagement />} />
        <Route path="devices/v2g/:id" element={<V2GDeviceDetail />} />
        <Route path="stations" element={<Stations />} />
        <Route path="workorders" element={<WorkOrders />} />
        <Route path="workorder-stats" element={<WorkOrderStats />} />
        <Route path="alarms" element={<Alarms />} />
        <Route path="reports" element={<Reports />} />
        <Route path="report-mgmt" element={<ReportMgmt />} />
        <Route path="teams" element={<Teams />} />
        <Route path="teams/engineers" element={<Engineers />} />
        <Route path="teams/roles" element={<TeamsRoles />} />
        <Route path="users" element={<Users />} />
        <Route path="health" element={<Health />} />
        <Route path="security" element={<Security />} />
        <Route path="inspection-ops" element={<InspectionOps />} />
        <Route path="telemetry" element={<TelemetryPage />} />
        <Route path="telemetry-classic" element={<TelemetryClassicPage />} />
        <Route path="fault-diagnosis" element={<FaultDiagnosisPage />} />
        <Route path="on-call" element={<OnCallPage />} />
        <Route path="smart-diagnosis" element={<SmartDiagnosisPage />} />
        <Route path="runbook" element={<RunbookPage />} />
        <Route path="healing" element={<HealingPage />} />
        <Route path="energy-report" element={<EnergyReportPage />} />
        <Route path="digital-twin" element={<DigitalTwinPage />} />
        <Route path="digital-twin/:stationId" element={<DigitalTwinPage />} />
        <Route path="vpp" element={<VPPPage />} />
        <Route path="predictive-maintenance" element={<PredictiveMaintenancePage />} />
        <Route path="ops-dashboard" element={<OpsDashboardPage />} />
        <Route path="analytics-dashboard" element={<AnalyticsDashboardPage />} />
        <Route path="reports/utilization" element={<UtilizationAnalysis />} />
        <Route path="reports/efficiency" element={<ChargeEfficiencyAnalysis />} />
        <Route path="reports/generation" element={<GenerationEfficiencyAnalysis />} />
        <Route path="monitor" element={<TelemetryPage />} />
        <Route path="diagnosis" element={<FaultDiagnosisPage />} />
        <Route path="alarm-notices" element={<Alarms />} />
        <Route path="api-keys" element={<ApiKeyPage />} />
        <Route path="log-analysis" element={<LogAnalysisPage />} />
        <Route path="notification-rules" element={<NotificationRulesPage />} />
        <Route path="message-center" element={<MessageCenterPage />} />
        <Route path="runbook-approval" element={<RunbookApprovalPage />} />
        <Route path="ssl-certificates" element={<SSLCertificatesPage />} />
        <Route path="webhooks" element={<WebhooksPage />} />
        <Route path="map" element={<Navigate to="/stations" replace />} />
        <Route path="operate" element={<Suspense fallback={<div style={{display:'flex',justifyContent:'center',alignItems:'center',height:'100%'}}><div style={{width:24,height:24,borderRadius:'50%',border:'2px solid #1890ff',borderTopColor:'transparent',animation:'spin 0.8s linear infinite'}} /></div>}><Operate /></Suspense>} />
        <Route path="operate/:tab" element={<Suspense fallback={<div style={{display:'flex',justifyContent:'center',alignItems:'center',height:'100%'}}><div style={{width:24,height:24,borderRadius:'50%',border:'2px solid #1890ff',borderTopColor:'transparent',animation:'spin 0.8s linear infinite'}} /></div>}><Operate /></Suspense>} />
        <Route path="fleet" element={<Suspense fallback={<div style={{display:'flex',justifyContent:'center',alignItems:'center',height:'100%'}}><div style={{width:24,height:24,borderRadius:'50%',border:'2px solid #1890ff',borderTopColor:'transparent',animation:'spin 0.8s linear infinite'}} /></div>}><Fleet /></Suspense>} />
        {/* 原 P0 独立页面已纳入 /operate Tabs, 旧路径兼容重定向 */}
        <Route path="discount-management" element={<Navigate to="/operate/discounts" replace />} />
        <Route path="coupon-management" element={<Navigate to="/operate/coupons" replace />} />
        <Route path="points-management" element={<Navigate to="/operate/points" replace />} />
        <Route path="user-type-management" element={<Navigate to="/operate/users" replace />} />
        {/* 互联互通+市政监管 已纳入 /operate Tabs, 旧路径重定向 */}
        <Route path="interconnect" element={<Navigate to="/operate/interconnect" replace />} />
        <Route path="supervision" element={<Navigate to="/operate/supervision" replace />} />
      </Route>

      {/* ======== 平台管理路由 (admin only) ======== */}
      <Route path="/platform" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<Navigate to="/platform/dashboard" replace />} />
        <Route path="dashboard" element={<PlatformDashboard />} />
      </Route>

      {/* ======== 系统管理员路由 ======== */}
      <Route path="/gateway" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<GatewayPage />} />
      </Route>

      <Route path="/device-library" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<DeviceLibraryPage />} />
      </Route>

      <Route path="/device-protocols" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<DeviceProtocolsPage />} />
      </Route>

      <Route path="/protocols" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<ProtocolsPage />} />
      </Route>

      <Route path="/tenants" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<TenantsPage />} />
        <Route path="data" element={<TenantsPage />} />
        <Route path="accounts" element={<TenantsPage />} />
      </Route>

      <Route path="/links" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<LinksPage />} />
      </Route>

      <Route path="/cloud" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<CloudPage />} />
      </Route>

      <Route path="/terminals" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<TerminalsPage />} />
      </Route>

      {/* 边缘网关 SN 平台台账 (任务卡 e940c9f4): 硬件发货生命周期管理 */}
      <Route path="/edge-gateways" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<EdgeGatewaysPage />} />
      </Route>

      {/* ======== 管理后台 - 物联网接入 (admin only) ======== */}
      <Route path="/admin" element={<Navigate to="/platform" replace />} />

      {/* ======== 经营驾驶舱 (拥有者视角, admin/operator 可见) ======== */}
      <Route path="/owner-cockpit" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin", "operator"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<OwnerCockpitPage />} />
      </Route>

      {/* 旧 admin/interconnect → 运营平台兼容重定向 */}
      <Route path="/admin/interconnect" element={<Navigate to="/operate/interconnect" replace />} />
      <Route path="/admin/supervision" element={<Navigate to="/operate/supervision" replace />} />
      <Route path="/knowledge" element={
        <ErrorBoundary>
          <RouteGuard>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<Knowledge />} />
        <Route path="detail/:id" element={<KnowledgeDetail />} />
        <Route path="edit/:id" element={<KnowledgeEdit />} />
        <Route path="create" element={<KnowledgeEdit />} />
      </Route>

      <Route path="/audit-log" element={
        <ErrorBoundary>
          <RouteGuard>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<AuditLogPage />} />
      </Route>

      <Route path="/data-ops" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<DataOpsPage />} />
      </Route>

      <Route path="/config" element={
        <ErrorBoundary>
          <RouteGuard>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<Config />} />
      </Route>

      <Route path="/ai-model_config" element={
        <ErrorBoundary>
          <RouteGuard allowedUserTypes={["admin"]}>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<AIModelConfigPage />} />
      </Route>

      {/* ======== RBAC 共享路由 ======== */}
      <Route path="/rbac" element={
        <ErrorBoundary>
          <RouteGuard>
            <AppLayout />
          </RouteGuard>
        </ErrorBoundary>
      }>
        <Route index element={<Navigate to="/rbac/users" replace />} />
        <Route path="users" element={<Users />} />
        <Route path="roles" element={<Rbac />} />
        <Route path="teams" element={<Teams />} />
        <Route path="teams/engineers" element={<Engineers />} />
      </Route>

      {/* 全局守卫 - 保护所有其他路由 */}
      <Route path="*" element={
        <RouteGuard>
          <Navigate to={(() => {
            const ut = getUserType();
            switch (ut) {
              case 'admin': return '/platform/dashboard';
              case 'engineer': return '/dashboard';
              case 'operator': return '/operate';
              case 'fleet': return '/fleet';
              default: return '/dashboard';
            }
          })()} replace />
        </RouteGuard>
      } />
    </Routes>
    {/* 天链助手 - AI对话浮窗 (登录页由 ChatPanel 内部 useLocation 屏蔽) */}
    <Suspense fallback={null}>
      <ChatPanel />
    </Suspense>
    </Suspense>
    </ErrorBoundary>
    </>
  );
}

export default App;