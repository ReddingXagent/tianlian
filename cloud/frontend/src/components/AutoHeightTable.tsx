/**
 * AutoHeightTable - 表格高度精确自适应（2026-10-09 丁哥: Mac/PC 底部大片闲置）
 *
 * 实时测量表格顶部到视口底部的距离, 表格体高度 = 视口剩余空间 - 分页器/边距,
 * 任何布局/屏幕/缩放比例下零留白, 替代 calc 估算方案。
 */
import React, { useEffect, useRef, useState } from 'react';
import { Table } from 'antd';
import type { TableProps } from 'antd';

interface AutoHeightTableProps<T> extends TableProps<T> {
  /** 表格体之下预留高度(分页器+间距), 默认 88 */
  bottomReserved?: number;
  /** 最小表格体高度, 默认 240 */
  minHeight?: number;
}

function AutoHeightTable<T extends object>({
  bottomReserved = 46,
  minHeight = 240,
  scroll,
  ...rest
}: AutoHeightTableProps<T>) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [bodyY, setBodyY] = useState(480);

  useEffect(() => {
    const update = () => {
      const el = wrapRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      // 分页器实际高度动态测量(2026-10-09 丁哥: 表格底线与左侧菜单底边对齐 → 撑满到视口底)
      const pager = el.querySelector('.ant-pagination');
      const pagerH = pager ? (pager as HTMLElement).offsetHeight + 12 : 56;
      const y = Math.max(minHeight, window.innerHeight - top - 55 - pagerH - 8);  // 8=底部细滚动条让位
      setBodyY((prev) => (Math.abs(prev - y) < 3 ? prev : y));
    };
    update();
    const timer = setTimeout(update, 300); // 布局稳定后再校一次
    window.addEventListener('resize', update);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', update);
    };
  }, [bottomReserved, minHeight]);

  return (
    <div ref={wrapRef}>
      <Table<T>
        scroll={{ ...scroll, y: bodyY }}
        {...rest}
      />
    </div>
  );
}

export default AutoHeightTable;
