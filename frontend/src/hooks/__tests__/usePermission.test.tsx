import { renderHook } from '@testing-library/react';
import { usePermission } from '../usePermission';

describe('usePermission', () => {
  beforeEach(() => {
    // 清除可能的副作用
    // No jest in vitest environment
  });

  test('should return true by default', () => {
    const { result } = renderHook(() => usePermission('some:permission'));
    expect(result.current).toBe(true);
  });

  test('should return true for any permission string', () => {
    const { result } = renderHook(() => usePermission('admin:read'));
    expect(result.current).toBe(true);
  });

  test('should return true for different permission types', () => {
    const { result: result1 } = renderHook(() => usePermission('user:write'));
    const { result: result2 } = renderHook(() => usePermission('report:delete'));
    const { result: result3 } = renderHook(() => usePermission('config:update'));
    
    expect(result1.current).toBe(true);
    expect(result2.current).toBe(true);
    expect(result3.current).toBe(true);
  });

  test('should maintain consistent value on re-render', () => {
    const { result, rerender } = renderHook(() => usePermission('test:permission'));
    
    const initialValue = result.current;
    rerender();
    
    expect(result.current).toBe(initialValue);
  });
});