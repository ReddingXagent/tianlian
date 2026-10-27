/**
 * 组件库索引 - 统一导出所有组件
 * 遵循统一组件库规范
 * 
 * Phase5 UI/UX优化:
 * - 新增 PageHeader (通用页面头部)
 * - 新增 StatusDot (状态指示器)
 * - 完善文档和导出
 */

// 布局组件
export { default as AdminLayout } from './Layout/AdminLayout';
export { default as PageHeader, PageHeaderSkeleton } from './PageHeader';

// 页面过渡
export { default as PageTransition } from './PageTransition';
export { default as PageWrapper } from './PageWrapper';

// 状态组件
export { default as LoadingSpinner } from './LoadingSpinner';
export { default as EmptyState } from './EmptyState';
export { default as Skeleton } from './Skeleton';
export { default as StatusDot } from './StatusDot';

// 图表组件
export { LineChart, BarChart, PieChart } from './Charts';

// 功能组件
export { default as ThemeToggle } from './ThemeToggle';
export { default as RouteGuard } from './RouteGuard';
export { default as ErrorBoundary } from './ErrorBoundary';
export { default as OfflineNotice } from './OfflineNotice';
export { default as VirtualList } from './VirtualList';
export { default as MaintenancePlanPanel } from './MaintenancePlanPanel';

// 导出类型
export type { default as LoadingSpinnerProps } from './LoadingSpinner';
export type { default as EmptyStateProps } from './EmptyState';
export type { StatusType } from './StatusDot';