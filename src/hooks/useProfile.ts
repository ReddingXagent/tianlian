import { useState, useCallback, useEffect } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { useAuthStore } from '../store/authStore';
import { authApi, statsApi } from '../services/api';
import { UserStats } from '../types';

interface UseProfileReturn {
  stats: UserStats | null;
  loadStats: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

export function useProfile(): UseProfileReturn {
  const { setUser } = useAuthStore();
  const [stats, setStats] = useState<UserStats | null>(null);
  const isFocused = useIsFocused();

  const loadStats = useCallback(async () => {
    try {
      const response = await statsApi.getUserStats();
      setStats(response.data);
    } catch {
      // 静默处理
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const response = await authApi.getProfile();
      setUser(response.data);
    } catch {
      // 静默处理
    }
  }, [setUser]);

  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) {
          loadStats();
          refreshProfile();
        }
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, loadStats, refreshProfile]);

  return {
    stats,
    loadStats,
    refreshProfile,
  };
}
