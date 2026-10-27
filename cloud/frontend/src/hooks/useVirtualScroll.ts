/**
 * 虚拟滚动 Hook
 *
 * 用于大量列表数据的高性能渲染
 * 只渲染可视区域内的行，大幅减少 DOM 节点
 */
import { useState, useRef, useCallback, useMemo, useEffect } from 'react';

export interface VirtualItem<T> {
  item: T;
  index: number;
  style: React.CSSProperties;
}

export interface UseVirtualScrollOptions<T> {
  items: T[];
  itemHeight: number;
  overscan?: number;
  containerHeight: number;
}

export interface UseVirtualScrollResult<T> {
  virtualItems: VirtualItem<T>[];
  totalHeight: number;
  containerRef: React.RefObject<HTMLDivElement>;
  scrollTo: (index: number) => void;
  onScroll: React.UIEventHandler<HTMLDivElement>;
}

export function useVirtualScroll<T>({
  items,
  itemHeight,
  overscan = 5,
  containerHeight,
}: UseVirtualScrollOptions<T>): UseVirtualScrollResult<T> {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);

  const totalHeight = items.length * itemHeight;

  const visibleCount = Math.ceil(containerHeight / itemHeight);
  const totalOverscan = overscan * 2 + visibleCount;

  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(
    items.length,
    Math.ceil(scrollTop / itemHeight) + totalOverscan
  );

  const virtualItems = useMemo(() => {
    const result: VirtualItem<T>[] = [];
    for (let i = startIndex; i < endIndex; i++) {
      result.push({
        item: items[i],
        index: i,
        style: {
          position: 'absolute' as const,
          top: 0,
          left: 0,
          width: '100%',
          height: itemHeight,
          transform: `translateY(${i * itemHeight}px)`,
        },
      });
    }
    return result;
  }, [items, startIndex, endIndex, itemHeight]);

  const handleScroll: React.UIEventHandler<HTMLDivElement> = useCallback((e) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setScrollTop((e.target as HTMLDivElement).scrollTop);
    });
  }, []);

  const scrollTo = useCallback((index: number) => {
    if (containerRef.current) {
      const target = index * itemHeight;
      containerRef.current.scrollTop = target;
      setScrollTop(target);
    }
  }, [itemHeight]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return {
    virtualItems,
    totalHeight,
    containerRef,
    scrollTo,
    onScroll: handleScroll,
  };
}