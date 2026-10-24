/**
 * DigitalTwin — Vitest 组件测试
 * 测试: StationOverview 渲染 + 加载状态 + 站点卡片交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock API ═══
const { mockStationAPI, mockDigitalTwinAPI, mockTelemetryAPI } = vi.hoisted(() => ({
  mockStationAPI: { businessList: vi.fn() },
  mockDigitalTwinAPI: {
    models: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
    scenes: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
    dataPoints: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
    listScenes: vi.fn(),
    getSceneLayout: vi.fn(),
    getRealtime: vi.fn(),
    initDefault: vi.fn(),
  },
  mockTelemetryAPI: { list: vi.fn() },
}));

vi.mock('../../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api')>();
  return {
    ...actual,
    stationAPI: mockStationAPI,
    digitalTwinAPI: mockDigitalTwinAPI,
    telemetryAPI: mockTelemetryAPI,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

const { mockUseParams } = vi.hoisted(() => ({
  mockUseParams: vi.fn(() => ({})),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useParams: mockUseParams,
    useNavigate: () => vi.fn(),
  };
});

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// Mock DigitalTwinCanvas (three.js dependency)
vi.mock('../components/DigitalTwinCanvas', () => ({
  default: () => React.createElement('div', { 'data-testid': 'canvas-mock' }, 'Canvas Mock'),
}));

vi.mock('../components/DevicePanel', () => ({
  default: () => React.createElement('div', { 'data-testid': 'device-panel-mock' }, 'DevicePanel Mock'),
}));

vi.mock('../components/SceneSettings', () => ({
  default: () => React.createElement('div', { 'data-testid': 'scene-settings-mock' }, 'SceneSettings Mock'),
}));

import DigitalTwinPage from '../index';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockUseParams.mockReturnValue({});
  mockStationAPI.businessList.mockResolvedValue({
    data: {
      items: [
        { id: 1, name: '测试站点Alpha', address: '北京市朝阳区', device_count: 12 },
        { id: 2, name: '测试站点Beta', address: '上海市浦东新区', device_count: 8 },
      ],
    },
  });
  mockDigitalTwinAPI.listScenes.mockResolvedValue({ scene: {} });
  mockDigitalTwinAPI.getSceneLayout.mockResolvedValue({ layout: {} });
  mockDigitalTwinAPI.getRealtime.mockResolvedValue({ data: {} });
});

// ═══ Tests ═══

describe('DigitalTwin 页面', () => {
  it('无 stationId 时显示站点总览页面', async () => {
    await act(async () => {
      render(
        <BrowserRouter>
          <DigitalTwinPage />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('数字孪生 - 站点总览')).toBeInTheDocument();
    });
  });

  it('站点总览渲染站点卡片', async () => {
    await act(async () => {
      render(
        <BrowserRouter>
          <DigitalTwinPage />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('测试站点Alpha')).toBeInTheDocument();
    });
    expect(screen.getByText('测试站点Beta')).toBeInTheDocument();
  });

  it('显示"选择站点进入3D可视化视图"提示', async () => {
    await act(async () => {
      render(
        <BrowserRouter>
          <DigitalTwinPage />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('选择站点进入3D可视化视图')).toBeInTheDocument();
    });
  });

  it('站点加载中显示 Spin 加载状态', async () => {
    // Make stationAPI.list hang — component shows Spin while waiting
    mockStationAPI.businessList.mockReturnValue(new Promise(() => {}));

    await act(async () => {
      render(
        <BrowserRouter>
          <DigitalTwinPage />
        </BrowserRouter>
      );
    });

    // Spin renders with ant-spin-spinning class
    const spin = document.querySelector('.ant-spin-spinning');
    expect(spin).toBeTruthy();
  });

  it('空站点列表显示空状态', async () => {
    mockStationAPI.businessList.mockResolvedValue({ data: { items: [] } });

    await act(async () => {
      render(
        <BrowserRouter>
          <DigitalTwinPage />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('暂无站点数据')).toBeInTheDocument();
    });
  });

  it('有 stationId 但加载失败时显示错误提示', async () => {
    // With stationId, the page calls useDigitalTwin which calls getRealtime.
    // getRealtime returns empty data, so station is null → shows error card
    mockUseParams.mockReturnValue({ stationId: '1' });

    await act(async () => {
      render(<BrowserRouter><DigitalTwinPage /></BrowserRouter>);
    });

    // Should NOT show station overview
    expect(screen.queryByText('数字孪生 - 站点总览')).not.toBeInTheDocument();
  });
});
