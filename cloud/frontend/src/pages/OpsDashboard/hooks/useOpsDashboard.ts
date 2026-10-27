/**
 * 运维大屏数据 Hook
 *
 * 封装拓扑/事件/健康度/概览数据拉取、30s 自动刷新、
 * 全屏切换、事件列表滚动等全部副作用与状态。
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import api from '../../../api';
import type { TopologyData, EventItem, HealthData, OverviewStats, NodePosition } from '../types';

export function useOpsDashboard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const eventListRef = useRef<HTMLDivElement>(null);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>('');
  // 刷新频率(秒): localStorage持久化, 刷新页面不丢(2026-10-10 丁哥)
  const [refreshInterval, setRefreshIntervalRaw] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem('ops_refresh_interval'));
      return v >= 30 && v <= 600 ? v : 30;
    } catch { return 30; }
  });
  const setRefreshInterval = (v: number) => {
    setRefreshIntervalRaw(v);
    try { localStorage.setItem('ops_refresh_interval', String(v)); } catch { /* 忽略 */ }
  };

  // 加载所有数据
  const loadAllData = useCallback(async () => {
    try {
      const [topoRes, eventRes, healthRes, overviewRes] = await Promise.allSettled([
        api.get('/ops-dashboard/topology'),
        api.get('/ops-dashboard/event-stream', { params: { limit: 50 } }),
        api.get('/ops-dashboard/health-scores'),
        api.get('/ops-dashboard/overview'),
      ]);

      if (topoRes.status === 'fulfilled') setTopology(topoRes.value.data);
      if (eventRes.status === 'fulfilled') setEvents(eventRes.value.data.events || []);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data);
      if (overviewRes.status === 'fulfilled') setOverview(overviewRes.value.data);

      setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
    } catch {
      // 静默处理：大屏数据加载失败保留上次状态
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, refreshInterval * 1000); // 可配置频率(秒, 大屏右上角设置)
    return () => clearInterval(interval);
  }, [refreshInterval, loadAllData]);

  // 全屏
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  // 事件自动滚动
  useEffect(() => {
    if (eventListRef.current) {
      eventListRef.current.scrollTop = 0;
    }
  }, [events]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  };

  return {
    containerRef,
    eventListRef,
    loading,
    topology,
    events,
    health,
    overview,
    selectedNode,
    setSelectedNode,
    lastUpdate,
    refreshInterval,
    setRefreshInterval,
    isFullscreen,
    toggleFullscreen,
  };
}
