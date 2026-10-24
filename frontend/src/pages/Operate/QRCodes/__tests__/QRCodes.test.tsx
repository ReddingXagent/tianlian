/**
 * 二维码管理 — Vitest 单元测试
 * 测试覆盖: 列表渲染(桩编号/站点/二维码状态) / 批量生成 / 单张下载PNG / 批量下载ZIP
 *
 * 字段契约来源: backend/app/api/v1/operate/charger_qrcode.py
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock 数据 — 严格按后端 list 真实字段
// ═══════════════════════════════════════════
const mockListData = {
  items: [
    {
      device_id: 1, device_name: '1号直流桩', device_code: 'DC001',
      device_type: 'charger_dc', station_name: '郑州充电站A',
      pile_code: 'MA000000000010000001', has_qrcode: true, is_active: true,
      print_count: 2, scan_count: 5, created_at: '2026-07-20T10:00:00',
    },
    {
      device_id: 2, device_name: '2号交流桩', device_code: 'AC001',
      device_type: 'charger_ac', station_name: '郑州充电站A',
      pile_code: null, has_qrcode: false, is_active: false,
      print_count: 0, scan_count: 0, created_at: null,
    },
  ],
  total: 2, page: 1, page_size: 20,
};

// ═══════════════════════════════════════════
// Mock API (api/index.ts default export)
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal() as Record<string, unknown>;
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

// blob 下载依赖 — jsdom 未实现 URL.createObjectURL
const createObjectURL = vi.fn(() => 'blob:mock-url');
const revokeObjectURL = vi.fn();

// ═══════════════════════════════════════════
// 导入组件 (在 mock 之后)
// ═══════════════════════════════════════════
import QRCodesPage from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  window.URL.createObjectURL = createObjectURL;
  window.URL.revokeObjectURL = revokeObjectURL;

  // GET: list / download
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/charger-qrcode/list')) {
      return Promise.resolve({ data: mockListData });
    }
    if (url.includes('/charger-qrcode/download/')) {
      return Promise.resolve({ data: new Blob(['png'], { type: 'image/png' }) });
    }
    return Promise.resolve({ data: {} });
  });
  // POST: generate / batch-download
  mockApi.post.mockImplementation((url: string) => {
    if (url.includes('/charger-qrcode/generate')) {
      return Promise.resolve({
        data: {
          generated: [{ device_id: 2, device_name: '2号交流桩', pile_code: 'MA000000000010000002', qr_image_url: '/api/v1/operate/charger-qrcode/download/2' }],
          errors: [], total: 1, failed: 0,
        },
      });
    }
    if (url.includes('/charger-qrcode/batch-download')) {
      return Promise.resolve({ data: new Blob(['zip'], { type: 'application/zip' }) });
    }
    return Promise.resolve({ data: {} });
  });
});

const renderPage = () =>
  render(
    <BrowserRouter>
      <QRCodesPage />
    </BrowserRouter>,
  );

// ═══════════════════════════════════════════
// 测试
// ═══════════════════════════════════════════
describe('QRCodes 二维码管理', () => {
  it('渲染充电桩列表(桩编号/站点/二维码状态)', async () => {
    renderPage();
    // 站点名
    await waitFor(() => expect(screen.getAllByText('郑州充电站A').length).toBeGreaterThan(0));
    // 桩编号(已生成的设备)
    expect(screen.getByText('MA000000000010000001')).toBeInTheDocument();
    // 设备名
    expect(screen.getByText('1号直流桩')).toBeInTheDocument();
  });

  it('勾选充电桩后点击「批量生成二维码」调用 generate 接口', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('1号直流桩')).toBeInTheDocument());

    // 点击表头全选 checkbox 选中所有行
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);

    // 点击批量生成
    const genBtn = screen.getByRole('button', { name: /批量生成二维码/ });
    fireEvent.click(genBtn);

    await waitFor(() => {
      const hit = mockApi.post.mock.calls.some(
        ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/generate'),
      );
      expect(hit).toBe(true);
    });
    // 验证入参 device_ids
    const genCall = mockApi.post.mock.calls.find(
      ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/generate'),
    );
    expect(genCall?.[1]).toEqual(
      expect.objectContaining({ device_ids: expect.arrayContaining([1, 2]) }),
    );
  });

  it('点击行内「下载PNG」触发单张下载接口', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('1号直流桩')).toBeInTheDocument());

    // 行内下载按钮(已生成二维码的设备 1)
    const dlBtn = screen.getAllByRole('button', { name: /下载PNG/ })[0];
    fireEvent.click(dlBtn);

    await waitFor(() => {
      const hit = mockApi.get.mock.calls.some(
        ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/download/1'),
      );
      expect(hit).toBe(true);
    });
    // 确认是 blob 请求
    const dlCall = mockApi.get.mock.calls.find(
      ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/download/1'),
    );
    expect(dlCall?.[1]).toEqual(expect.objectContaining({ responseType: 'blob' }));
  });

  it('勾选后点击「批量下载ZIP」触发 batch-download 接口', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('1号直流桩')).toBeInTheDocument());

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); // 全选

    fireEvent.click(screen.getByRole('button', { name: /批量下载ZIP/ }));

    await waitFor(() => {
      const hit = mockApi.post.mock.calls.some(
        ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/batch-download'),
      );
      expect(hit).toBe(true);
    });
    const batchCall = mockApi.post.mock.calls.find(
      ([url]) => typeof url === 'string' && url.includes('/charger-qrcode/batch-download'),
    );
    expect(batchCall?.[1]).toEqual(
      expect.objectContaining({ device_ids: expect.arrayContaining([1, 2]) }),
    );
    expect(batchCall?.[2]).toEqual(expect.objectContaining({ responseType: 'blob' }));
  });

  it('预览列对已生成二维码的设备渲染真实二维码缩略图(SVG)而非仅图标', async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('1号直流桩')).toBeInTheDocument());

    // 已生成二维码的行(device 1, has_qrcode=true)预览列渲染真实二维码 SVG 缩略图
    const thumbnails = container.querySelectorAll('svg.qr-preview-thumbnail');
    expect(thumbnails.length).toBe(1);

    // 未生成二维码的行(device 2, has_qrcode=false)预览列不渲染缩略图
    // -> 全表二维码缩略图数量 == 已生成二维码行数(仅 device 1)
  });

  it('hover 预览缩略图弹出放大的二维码(Popover)', async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('1号直流桩')).toBeInTheDocument());

    const thumbnail = container.querySelector('svg.qr-preview-thumbnail');
    expect(thumbnail).toBeTruthy();
    // Popover trigger 是包裹缩略图的 <span>
    fireEvent.mouseEnter(thumbnail!.parentElement!);

    // 放大版二维码通过 Portal 渲染到 document.body
    await waitFor(() => {
      const large = document.body.querySelectorAll('svg.qr-preview-large');
      expect(large.length).toBe(1);
    });
  });
});
