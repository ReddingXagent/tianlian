/**
 * 天链V3 — 数据大屏数据加载 Hook
 *
 * Phase48: 封装 LargeScreen 的数据拉取、定时刷新、页面轮播状态
 *
 * 功能：
 * - 拉取 /dashboard/large-screen 数据
 * - 每30秒自动刷新
 * - API 失败时进入错误态（不回退假数据，挂墙大屏不能演假站点）
 * - 每30秒轮播切换页面（共3页）
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import api from '../../../api';
import type { LargeScreenData } from '../types';

export function useLargeScreenData() {
  const [data, setData] = useState<LargeScreenData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const fetchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rotateTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── 数据加载 ──
  const fetchData = useCallback(async () => {
    try {
      const res = await api.get('/dashboard/large-screen');
      setData(res.data);
      setError(null);
    } catch {
      setError('数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // 每30秒刷新数据
    fetchTimerRef.current = setInterval(fetchData, 30000);
    // 每30秒轮播切换页面
    rotateTimerRef.current = setInterval(() => {
      setPageIndex(prev => (prev + 1) % 3);
    }, 30000);

    return () => {
      if (fetchTimerRef.current) clearInterval(fetchTimerRef.current);
      if (rotateTimerRef.current) clearInterval(rotateTimerRef.current);
    };
  }, [fetchData]);

  return { data, loading, error, pageIndex, setPageIndex, refresh: fetchData };
}
