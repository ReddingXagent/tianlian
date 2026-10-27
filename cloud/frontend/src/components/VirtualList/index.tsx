/**
 * VirtualList - 虚拟滚动列表组件
 *
 * 用于大量数据的高性能渲染
 * 只渲染可视区域内的 DOM 节点
 */
import React, { useCallback } from 'react';
import { useVirtualScroll } from '../../hooks/useVirtualScroll';

interface VirtualListProps<T> {
  items: T[];
  itemHeight: number;
  containerHeight: number;
  overscan?: number;
  renderItem: (item: T, index: number) => React.ReactNode;
  onScroll?: React.UIEventHandler<HTMLDivElement>;
  className?: string;
}

function VirtualList<T>({
  items,
  itemHeight,
  containerHeight,
  overscan = 5,
  renderItem,
  onScroll,
  className,
}: VirtualListProps<T>) {
  const {
    virtualItems,
    totalHeight,
    containerRef,
    onScroll: defaultOnScroll,
  } = useVirtualScroll<T>({
    items,
    itemHeight,
    overscan,
    containerHeight,
  });

  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      defaultOnScroll(e);
      onScroll?.(e);
    },
    [defaultOnScroll, onScroll]
  );

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{
        height: containerHeight,
        overflow: 'auto',
        position: 'relative',
      }}
      className={className}
    >
      <div style={{ height: totalHeight, position: 'relative' }}>
        {virtualItems.map(({ item, index, style }) => (
          <div key={index} style={style}>
            {renderItem(item, index)}
          </div>
        ))}
      </div>
    </div>
  );
}

export default VirtualList;