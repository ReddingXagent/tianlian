/**
 * AutoScrollbar - 表格底部贴合式横向滚动条（v3, 2026-10-09）
 *
 * v2(视口底部悬浮中央)被反馈"单独占一行浪费空间" → v3:
 *   - 定位到当前激活表格的底边(宽度与表格对齐), 不单独占行
 *   - 表格底部超出视口时自动回落贴视口底
 *   - 无悬停表格时完全隐藏(零占用)
 */
import { useEffect } from 'react';

const AutoScrollbar: React.FC = () => {
  useEffect(() => {
    const bar = document.createElement('div');
    bar.className = 'autosb-bar';
    const thumb = document.createElement('div');
    thumb.className = 'autosb-thumb';
    bar.appendChild(thumb);
    document.body.appendChild(bar);

    let active: HTMLElement | null = null;

    const findScrollable = (el: Element | null): HTMLElement | null => {
      let node = el;
      while (node && node !== document.body) {
        if (
          node instanceof HTMLElement &&
          node.classList.contains('ant-table-body') &&
          node.scrollWidth - node.clientWidth > 8
        ) {
          return node;
        }
        node = node.parentElement;
      }
      return null;
    };

    const sync = () => {
      if (!active) {
        bar.style.opacity = '0';
        bar.style.pointerEvents = 'none';
        return;
      }
      const t = active;
      const overflow = t.scrollWidth - t.clientWidth;
      if (overflow <= 8) {
        bar.style.opacity = '0';
        bar.style.pointerEvents = 'none';
        return;
      }
      // 宽度仍对齐表格组件; 高度改为细条8px恒贴视口底(不遮挡表格/分页器, 右下角完整)
      const wrapper = t.closest('.ant-table-wrapper');
      const anchor = (wrapper as HTMLElement) || t;
      const rect = anchor.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      bar.style.bottom = '0px';  // 恒贴视口底(与菜单底边线重合)
      bar.style.left = `${Math.max(4, rect.left)}px`;
      bar.style.width = `${Math.max(120, Math.min(rect.width, vw - 16) - 8)}px`;
      bar.style.opacity = '1';
      bar.style.pointerEvents = 'auto';
      const innerW = Math.min(rect.width, vw - 16) - 20;
      const ratio = t.clientWidth / t.scrollWidth;
      const thumbW = Math.max(44, Math.round(innerW * ratio));
      const maxLeft = innerW - thumbW;
      const left = Math.round((t.scrollLeft / overflow) * Math.max(0, maxLeft));
      thumb.style.width = `${thumbW}px`;
      thumb.style.transform = `translateX(${6 + left}px)`;
    };

    const onOver = (e: MouseEvent) => {
      const t = findScrollable(e.target as Element);
      if (t) {
        active = t;
        sync();
      }
    };
    document.addEventListener('mouseover', onOver, { passive: true });

    const onScroll = (e: Event) => {
      if (e.target === active) sync();
    };
    document.addEventListener('scroll', onScroll, { capture: true, passive: true });

    // 拖动 thumb → 滚动表格
    let dragging = false;
    let startX = 0;
    let startScroll = 0;
    const onDown = (e: MouseEvent) => {
      if (!active) return;
      dragging = true;
      startX = e.clientX;
      startScroll = active.scrollLeft;
      thumb.classList.add('dragging');
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging || !active) return;
      const t = active;
      const overflow = t.scrollWidth - t.clientWidth;
      const ratio = t.clientWidth / t.scrollWidth;
      const rect = bar.getBoundingClientRect();
      const thumbW = Math.max(44, Math.round((rect.width - 20) * ratio));
      const maxLeft = rect.width - 20 - thumbW;
      if (maxLeft <= 0) return;
      t.scrollLeft = startScroll + ((e.clientX - startX) * overflow) / maxLeft;
    };
    const onUp = () => {
      dragging = false;
      thumb.classList.remove('dragging');
    };
    thumb.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);

    const onBarClick = (e: MouseEvent) => {
      if (!active || e.target === thumb) return;
      const rect = bar.getBoundingClientRect();
      const x = e.clientX - rect.left;
      active.scrollLeft = (x / rect.width) * active.scrollWidth - active.clientWidth / 2;
    };
    bar.addEventListener('mousedown', onBarClick);

    const onResize = () => sync();
    window.addEventListener('resize', onResize);
    const mo = new MutationObserver(() => sync());
    mo.observe(document.body, { childList: true, subtree: true });
    sync();

    return () => {
      document.removeEventListener('mouseover', onOver);
      document.removeEventListener('scroll', onScroll, { capture: true } as any);
      thumb.removeEventListener('mousedown', onDown);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('resize', onResize);
      bar.removeEventListener('mousedown', onBarClick);
      mo.disconnect();
      bar.remove();
    };
  }, []);

  return null;
};

export default AutoScrollbar;
