// src/store/brandingStore.ts - 多租户品牌状态管理
import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { tenantApi } from '../services/api';
import type { TenantBranding } from '../types';

const CACHE_KEY = 'tianlian_tenant_branding';
const CACHE_TTL = 300000; // 5min

interface BrandingState {
  branding: TenantBranding | null;
  loading: boolean;
  error: string | null;
  loadBranding: (tenantId: string) => Promise<void>;
  loadFromCache: () => Promise<TenantBranding | null>;
  reset: () => void;
}

export const useBrandingStore = create<BrandingState>((set) => ({
  branding: null,
  loading: false,
  error: null,

  loadFromCache: async () => {
    try {
      const raw = await SecureStore.getItemAsync(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { data: TenantBranding; expiredAt: number };
      if (parsed.expiredAt && Date.now() > parsed.expiredAt) return null;
      return parsed.data;
    } catch {
      return null;
    }
  },

  loadBranding: async (tenantId: string) => {
    set({ loading: true, error: null });
    try {
      const res = await tenantApi.getBranding(tenantId);
      const data = res.data;
      set({ branding: data, loading: false });
      // 缓存
      try {
        await SecureStore.setItemAsync(
          CACHE_KEY,
          JSON.stringify({ data, cachedAt: Date.now(), expiredAt: Date.now() + CACHE_TTL })
        );
      } catch {
        // 缓存失败静默
      }
    } catch (err) {
      // 降级：读缓存
      const cached = await useBrandingStore.getState().loadFromCache();
      if (cached) {
        set({ branding: cached, loading: false, error: null });
      } else {
        set({
          branding: {
            tenantId,
            operatorName: '天链',
            themeColor: '#00A86B',
            source: 'default',
          },
          loading: false,
          error: err instanceof Error ? err.message : '加载品牌失败',
        });
      }
    }
  },

  reset: () => {
    set({ branding: null, loading: false, error: null });
    SecureStore.deleteItemAsync(CACHE_KEY).catch(() => {});
  },
}));
