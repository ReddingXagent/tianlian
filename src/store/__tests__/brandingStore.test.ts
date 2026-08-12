import { tenantApi } from '../../services/api';
import { useBrandingStore } from '../brandingStore';
import type { TenantBranding } from '../../types';

// Mock expo-secure-store (already mapped in jest moduleNameMapper, but ensure isolated behavior)
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/api', () => ({
  tenantApi: {
    getBranding: jest.fn(),
  },
}));

const mockBranding: TenantBranding = {
  tenantId: 'tenant-001',
  operatorName: '测试运营商',
  logoUrl: 'https://example.com/logo.png',
  themeColor: '#FF5733',
  source: 'operator',
};

describe('brandingStore', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useBrandingStore.setState({
      branding: null,
      loading: false,
      error: null,
    });
  });

  describe('loadBranding', () => {
    it('should fetch and set branding', async () => {
      (tenantApi.getBranding as jest.Mock).mockResolvedValue({ data: mockBranding });

      await useBrandingStore.getState().loadBranding('tenant-001');

      expect(tenantApi.getBranding).toHaveBeenCalledWith('tenant-001');
      const state = useBrandingStore.getState();
      expect(state.branding).toEqual(mockBranding);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should set loading true while fetching', async () => {
      (tenantApi.getBranding as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ data: mockBranding }), 100))
      );

      const promise = useBrandingStore.getState().loadBranding('tenant-001');
      expect(useBrandingStore.getState().loading).toBe(true);
      await promise;
    });

    it('should fallback to default branding on API failure', async () => {
      (tenantApi.getBranding as jest.Mock).mockRejectedValue(new Error('网络错误'));

      await useBrandingStore.getState().loadBranding('tenant-002');

      const state = useBrandingStore.getState();
      expect(state.loading).toBe(false);
      expect(state.branding).not.toBeNull();
      expect(state.branding!.tenantId).toBe('tenant-002');
      expect(state.branding!.source).toBe('default');
      expect(state.branding!.operatorName).toBe('天链');
      expect(state.error).toBe('网络错误');
    });

    it('should use fallback error message for non-Error thrown', async () => {
      (tenantApi.getBranding as jest.Mock).mockRejectedValue('timeout');

      await useBrandingStore.getState().loadBranding('tenant-003');

      const state = useBrandingStore.getState();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('加载品牌失败');
    });
  });

  describe('loadFromCache', () => {
    it('should return cached branding when valid', async () => {
      const cached = { data: mockBranding, cachedAt: Date.now(), expiredAt: Date.now() + 60000 };
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').getItemAsync as jest.Mock).mockResolvedValue(JSON.stringify(cached));

      const result = await useBrandingStore.getState().loadFromCache();
      expect(result).toEqual(mockBranding);
    });

    it('should return null when cache expired', async () => {
      const expired = { data: mockBranding, cachedAt: 0, expiredAt: 1 };
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').getItemAsync as jest.Mock).mockResolvedValue(JSON.stringify(expired));

      const result = await useBrandingStore.getState().loadFromCache();
      expect(result).toBeNull();
    });

    it('should return null on JSON parse error', async () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').getItemAsync as jest.Mock).mockResolvedValue('invalid-json');

      const result = await useBrandingStore.getState().loadFromCache();
      expect(result).toBeNull();
    });
  });

  describe('loadBranding cache fallback', () => {
    it('should use cached branding when API fails and cache exists', async () => {
      const cached = { data: mockBranding, cachedAt: Date.now(), expiredAt: Date.now() + 60000 };
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').getItemAsync as jest.Mock).mockResolvedValue(JSON.stringify(cached));
      (tenantApi.getBranding as jest.Mock).mockRejectedValue(new Error('网络错误'));

      await useBrandingStore.getState().loadBranding('tenant-001');

      const state = useBrandingStore.getState();
      expect(state.branding).toEqual(mockBranding);
      expect(state.error).toBeNull();
      expect(state.loading).toBe(false);
    });

    it('should silently handle setItemAsync failure', async () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').setItemAsync as jest.Mock).mockRejectedValue(new Error('disk full'));
      (tenantApi.getBranding as jest.Mock).mockResolvedValue({ data: mockBranding });

      await useBrandingStore.getState().loadBranding('tenant-001');

      const state = useBrandingStore.getState();
      expect(state.branding).toEqual(mockBranding);
      expect(state.loading).toBe(false);
    });
  });

  describe('reset', () => {
    it('should clear branding and loading state', () => {
      useBrandingStore.setState({ branding: mockBranding, loading: true, error: 'some error' });

      useBrandingStore.getState().reset();

      const state = useBrandingStore.getState();
      expect(state.branding).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should silently handle deleteItemAsync failure', () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('expo-secure-store').deleteItemAsync as jest.Mock).mockRejectedValue(new Error('permission'));

      expect(() => useBrandingStore.getState().reset()).not.toThrow();

      const state = useBrandingStore.getState();
      expect(state.branding).toBeNull();
    });
  });
});
