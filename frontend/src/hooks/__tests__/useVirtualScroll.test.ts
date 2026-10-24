/**
 * useVirtualScroll Hook 测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVirtualScroll } from '../useVirtualScroll';

interface TestItem {
  id: number;
  name: string;
}

const ITEM_HEIGHT = 40;
const CONTAINER_HEIGHT = 400;

describe('useVirtualScroll', () => {
  let items: TestItem[];

  beforeEach(() => {
    items = Array.from({ length: 100 }, (_, i) => ({
      id: i,
      name: `Item ${i}`,
    }));
  });

  it('should calculate total height correctly', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );
    expect(result.current.totalHeight).toBe(items.length * ITEM_HEIGHT);
  });

  it('should render visible items only', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    const visibleCount = Math.ceil(CONTAINER_HEIGHT / ITEM_HEIGHT);
    const expectedCount = visibleCount + 5 * 2; // visible + overscan

    expect(result.current.virtualItems.length).toBeLessThanOrEqual(expectedCount);
    expect(result.current.virtualItems.length).toBeGreaterThan(0);
  });

  it('should include overscan items', () => {
    const overscan = 3;
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        overscan,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    const visibleCount = Math.ceil(CONTAINER_HEIGHT / ITEM_HEIGHT);
    const expectedCount = visibleCount + overscan * 2;

    expect(result.current.virtualItems.length).toBe(expectedCount);
  });

  it('should start from index 0', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(result.current.virtualItems[0].index).toBe(0);
    expect(result.current.virtualItems[0].item.id).toBe(0);
  });

  it('should set correct position styles', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    const firstItem = result.current.virtualItems[0];
    expect(firstItem.style.position).toBe('absolute');
    expect(firstItem.style.height).toBe(ITEM_HEIGHT);
    expect(firstItem.style.transform).toBe(`translateY(0px)`);
  });

  it('should offset items by their index', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    for (const virtualItem of result.current.virtualItems) {
      expect(virtualItem.style.transform).toBe(
        `translateY(${virtualItem.index * ITEM_HEIGHT}px)`
      );
    }
  });

  it('should handle empty items array', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items: [],
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(result.current.totalHeight).toBe(0);
    expect(result.current.virtualItems).toEqual([]);
  });

  it('should handle single item', () => {
    const singleItem = [{ id: 0, name: 'Only' }];
    const { result } = renderHook(() =>
      useVirtualScroll({
        items: singleItem,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(result.current.totalHeight).toBe(ITEM_HEIGHT);
    expect(result.current.virtualItems.length).toBe(1);
    expect(result.current.virtualItems[0].index).toBe(0);
  });

  it('should return containerRef', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(result.current.containerRef).toBeDefined();
    expect(result.current.containerRef.current).toBeNull();
  });

  it('should return onScroll handler', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(typeof result.current.onScroll).toBe('function');
  });

  it('should provide scrollTo function', () => {
    const { result } = renderHook(() =>
      useVirtualScroll({
        items,
        itemHeight: ITEM_HEIGHT,
        containerHeight: CONTAINER_HEIGHT,
      })
    );

    expect(typeof result.current.scrollTo).toBe('function');
    // scrollTo should not throw when ref is null
    expect(() => result.current.scrollTo(10)).not.toThrow();
  });

  it('should update virtualItems when items change', () => {
    const { result, rerender } = renderHook(
      ({ items: i }) =>
        useVirtualScroll({
          items: i,
          itemHeight: ITEM_HEIGHT,
          containerHeight: CONTAINER_HEIGHT,
        }),
      { initialProps: { items } }
    );

    const initialLength = result.current.virtualItems.length;

    const moreItems = [
      ...items,
      { id: 100, name: 'Extra' },
      { id: 101, name: 'Extra2' },
    ];

    rerender({ items: moreItems });

    expect(result.current.totalHeight).toBe(moreItems.length * ITEM_HEIGHT);
  });
});
