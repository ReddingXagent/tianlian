/**
 * 骨架屏组件 - 为数据加载页面提供骨架占位
 * 支持: Dashboard / Table / Card / Detail 多种布局模式
 */
import React from 'react';
import { Skeleton as AntSkeleton } from 'antd';

interface SkeletonPageProps {
  type?: 'dashboard' | 'table' | 'card' | 'detail' | 'list';
  count?: number;
}

/** 页面级骨架屏 */
const SkeletonPage: React.FC<SkeletonPageProps> = ({ type = 'table', count = 5 }) => {
  switch (type) {
    case 'dashboard':
      return <DashboardSkeleton />;
    case 'table':
      return <TableSkeleton rows={count} />;
    case 'card':
      return <CardGridSkeleton count={count} />;
    case 'detail':
      return <DetailSkeleton />;
    case 'list':
      return <ListSkeleton count={count} />;
    default:
      return <TableSkeleton rows={count} />;
  }
};

/** Dashboard 骨架屏 - 顶部统计卡片 + 图表区 */
const DashboardSkeleton: React.FC = () => (
  <div className="dash-container" style={{ padding: 24 }}>
    {/* 头部区域 */}
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
      <AntSkeleton.Input active style={{ width: 200, height: 32 }} />
      <div style={{ display: 'flex', gap: 8 }}>
        <AntSkeleton.Button active style={{ width: 60 }} />
        <AntSkeleton.Button active style={{ width: 80 }} />
      </div>
    </div>
    {/* 统计卡片行 */}
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
      gap: 16,
      marginBottom: 24,
    }}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20, boxShadow: 'var(--shadow-sm)' }}>
          <AntSkeleton active paragraph={{ rows: 0 }} title={{ width: '60%' }} />
          <AntSkeleton.Input active style={{ width: '40%', height: 36, marginTop: 12 }} />
          <AntSkeleton.Input active style={{ width: '80%', height: 16, marginTop: 8 }} />
        </div>
      ))}
    </div>
    {/* 图表区 */}
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
      gap: 16,
    }}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20, boxShadow: 'var(--shadow-sm)' }}>
          <AntSkeleton active paragraph={{ rows: 0 }} title={{ width: '40%' }} />
          <AntSkeleton.Node active style={{ width: '100%', height: 200, marginTop: 16 }}>
            <div />
          </AntSkeleton.Node>
        </div>
      ))}
    </div>
  </div>
);

/** 表格骨架屏 */
const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="page-container">
    {/* 标题 + 操作区 */}
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
      <AntSkeleton.Input active style={{ width: 180, height: 28 }} />
      <AntSkeleton.Button active style={{ width: 100, height: 36 }} />
    </div>
    {/* 搜索/筛选区 */}
    <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 16, marginBottom: 16, boxShadow: 'var(--shadow-sm)' }}>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {[1, 2, 3, 4].map(i => (
          <AntSkeleton.Input key={i} active style={{ width: 180, height: 36 }} />
        ))}
      </div>
    </div>
    {/* 表格骨架 */}
    <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 8, boxShadow: 'var(--shadow-sm)' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-color)' }}>
          <AntSkeleton.Input active style={{ width: '100%', height: 20 }} />
        </div>
      ))}
    </div>
  </div>
);

/** 卡片网格骨架屏 */
const CardGridSkeleton: React.FC<{ count?: number }> = ({ count = 6 }) => (
  <div className="page-container">
    <AntSkeleton.Input active style={{ width: 180, height: 28, marginBottom: 24 }} />
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
      gap: 16,
    }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20, boxShadow: 'var(--shadow-sm)' }}>
          <AntSkeleton active paragraph={{ rows: 0 }} title={{ width: '70%' }} />
          <AntSkeleton.Input active style={{ width: '100%', height: 16, marginTop: 12 }} />
          <AntSkeleton.Input active style={{ width: '80%', height: 16, marginTop: 8 }} />
          <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
            <AntSkeleton.Button active style={{ width: 60 }} />
            <AntSkeleton.Button active style={{ width: 60 }} />
          </div>
        </div>
      ))}
    </div>
  </div>
);

/** 详情页骨架屏 */
const DetailSkeleton: React.FC = () => (
  <div className="page-container" style={{ maxWidth: 800 }}>
    <AntSkeleton.Input active style={{ width: 240, height: 32, marginBottom: 24 }} />
    <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 24, boxShadow: 'var(--shadow-sm)' }}>
      <AntSkeleton active paragraph={{ rows: 1 }} title={{ width: '50%' }} />
      <div style={{ margin: '20px 0', height: 1, background: 'var(--border-color)' }} />
      {[1, 2, 3, 4, 5, 6].map(i => (
        <div key={i} style={{ display: 'flex', gap: 40, marginBottom: 16 }}>
          <AntSkeleton.Input active style={{ width: 80, height: 16 }} />
          <AntSkeleton.Input active style={{ width: 200, height: 16 }} />
        </div>
      ))}
      <div style={{ margin: '20px 0', height: 1, background: 'var(--border-color)' }} />
      <AntSkeleton active paragraph={{ rows: 3 }} />
    </div>
  </div>
);

/** 列表骨架屏 */
const ListSkeleton: React.FC<{ count?: number }> = ({ count = 5 }) => (
  <div className="page-container">
    <AntSkeleton.Input active style={{ width: 180, height: 28, marginBottom: 16 }} />
    <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 16, boxShadow: 'var(--shadow-sm)' }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 16, padding: '12px 0', borderBottom: '1px solid var(--border-color)' }}>
          <AntSkeleton.Avatar active style={{ width: 48, height: 48 }} />
          <div style={{ flex: 1 }}>
            <AntSkeleton.Input active style={{ width: '60%', height: 18 }} />
            <AntSkeleton.Input active style={{ width: '90%', height: 14, marginTop: 8 }} />
          </div>
        </div>
      ))}
    </div>
  </div>
);

export default SkeletonPage;
export { DashboardSkeleton, TableSkeleton, CardGridSkeleton, DetailSkeleton, ListSkeleton };
