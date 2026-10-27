/**
 * 天链V3 — 数据大屏页面导航点
 *
 * Phase48: 右侧固定导航圆点，点击切换轮播页面
 */
import React from 'react';
import { PRIMARY_COLOR } from '../constants';

const PageDots: React.FC<{
  pageIndex: number;
  onSelect: (index: number) => void;
}> = ({ pageIndex, onSelect }) => (
  <div
    style={{
      position: 'fixed',
      right: 16,
      top: '50%',
      transform: 'translateY(-50%)',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      zIndex: 100,
    }}
  >
    {[0, 1, 2].map((i) => (
      <div
        key={i}
        onClick={() => onSelect(i)}
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: pageIndex === i ? PRIMARY_COLOR : 'rgba(255,255,255,0.2)',
          cursor: 'pointer',
          transition: 'all 0.3s',
          boxShadow: pageIndex === i ? `0 0 8px ${PRIMARY_COLOR}` : 'none',
        }}
      />
    ))}
  </div>
);

export default PageDots;
