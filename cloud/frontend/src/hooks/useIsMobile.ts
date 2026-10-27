/**
 * useIsMobile - 响应式断点检测 Hook
 *
 * 视口宽度 < maxWidth 时返回 true，用于驱动移动端/桌面端的布局分支切换。
 *
 * 采用 window.innerWidth + resize 监听（而非 matchMedia），原因：
 *   1. 与 AdminLayout 既有响应式实现保持一致，统一断点来源；
 *   2. jsdom/happy-dom 测试环境下 matchMedia 被 stub 为 matches:false 无法响应宽度变化，
 *      而 innerWidth 可由 vi.stubGlobal('innerWidth', N) + dispatchEvent('resize') 精确驱动。
 *
 * 不写死 px 魔法数：maxWidth 默认取自 ui-constants.breakpoints.mobile(768)，
 * 调用方亦传入 breakpoints.tablet(1024) 等做其它断点判断。
 *
 * 用法:
 *   const isMobile = useIsMobile();                                          // <768
 *   const isTablet = useIsMobile(breakpoints.tablet) && !isMobile;           // 768≤w<1024
 */
import { useEffect, useState } from 'react';
import { breakpoints } from '../styles/ui-constants';

export function useIsMobile(maxWidth: number = breakpoints.mobile): boolean {
  const [match, setMatch] = useState<boolean>(
    () => (typeof window !== 'undefined' ? window.innerWidth < maxWidth : false)
  );

  useEffect(() => {
    const update = () => setMatch(window.innerWidth < maxWidth);
    // 挂载时立即同步一次，避免 maxWidth 变化或初始 innerWidth 与 SSR 预设不一致
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [maxWidth]);

  return match;
}

export default useIsMobile;
