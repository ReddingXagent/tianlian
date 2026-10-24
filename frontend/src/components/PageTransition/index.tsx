/**
 * 页面过渡动画组件
 * 提供页面切换动画 + 按钮hover/click反馈
 */
import React from 'react';
import type { ReactNode } from 'react';
import './PageTransition.css';

interface PageTransitionProps {
  children: ReactNode;
  /** 动画类型 */
  effect?: 'fade' | 'slide-up' | 'slide-left' | 'scale';
  /** 延迟 (ms) */
  delay?: number;
  /** 额外 className */
  className?: string;
}

/** 页面过渡包装器 - 用于 Outlet 包裹 */
const PageTransition: React.FC<PageTransitionProps> = ({
  children,
  effect = 'fade',
  delay = 0,
  className = '',
}) => (
  <div
    className={`page-transition page-${effect} ${className}`}
    style={{ animationDelay: `${delay}ms` }}
  >
    {children}
  </div>
);

/** 列表项交错入场 (staggered) */
interface StaggerListProps {
  children: ReactNode[];
  className?: string;
  /** 每项延迟间隔 (ms) */
  staggerDelay?: number;
  /** 方向 */
  effect?: 'fade-up' | 'fade-left' | 'scale';
}

const StaggerList: React.FC<StaggerListProps> = ({
  children,
  className = '',
  staggerDelay = 80,
  effect = 'fade-up',
}) => {
  const items = React.Children.toArray(children);
  return (
    <>
      {items.map((child, i) => (
        <div
          key={i}
          className={`stagger-item stagger-${effect} ${className}`}
          style={{ animationDelay: `${i * staggerDelay}ms` }}
        >
          {child}
        </div>
      ))}
    </>
  );
};

export default PageTransition;
export { StaggerList };
