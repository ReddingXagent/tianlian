/**
 * Webhook 管理页面 — Vitest 单元测试
 *
 * 页面使用 `import api from '../../api'` (default 导出)，内部 webhookAPI
 * 直接调用 api.get/post/put/delete。列表解包路径为 resp.data.data.{items,total}。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API — default export (axios instance)
// ═══════════════════════════════════════════
const { mockApi, mockMessage } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  // message.loading 必须返回一个 hide 函数，否则 handleTest 调用 hide() 会抛错
  mockMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    loading: vi.fn(() => () => {}),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: mockMessage,
  };
});

import WebhooksPage from '../index';

// ═══════════════════════════════════════════
// 测试数据 — 注意双层 data 包裹 (resp.data.data)
// ═══════════════════════════════════════════
const mockWebhooks = {
  data: {
    items: [
      {
        id: 1,
        name: '告警回调',
        url: 'https://alert.example.com/hook',
        event_types: ['alert', 'device'],
        secret: 'sig-secret',
        retry_count: 3,
        retry_interval: 60,
        timeout: 10,
        enabled: true,
        description: '告警通知',
      },
      {
        id: 2,
        name: '订单回调',
        url: 'https://order.example.com/hook',
        event_types: ['order'],
        retry_count: 5,
        retry_interval: 30,
        timeout: 15,
        enabled: false,
        description: '',
      },
    ],
    total: 2,
  },
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: mockWebhooks });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

describe('Webhook 管理 — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
      container = c;
    });
    expect(container!).toBeTruthy();
  });

  it('渲染标题、搜索框与新建按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');
    expect(screen.getByText('Webhook 管理')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('搜索名称/URL')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /新建\s*Webhook/ })).toBeInTheDocument();
  });

  it('挂载时调用列表接口 /webhooks', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/webhooks',
        expect.objectContaining({ params: expect.objectContaining({ page: 1 }) }),
      );
    });
  });

  it('加载后表格渲染 Webhook 行数据与分页总数', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    expect(await screen.findByText('告警回调')).toBeInTheDocument();
    expect(screen.getByText('订单回调')).toBeInTheDocument();
    // 分页 showTotal 文案: 共 2 条
    expect(screen.getByText(/共\s*2\s*条/)).toBeInTheDocument();
  });
});

describe('Webhook 管理 — 交互', () => {
  it('点击新建按钮打开创建弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /新建\s*Webhook/ }));
    });

    // Modal 独有字段（表头也有 "回调 URL"，故用 "订阅事件类型" 判定弹窗打开）
    await waitFor(() => {
      expect(screen.getByText('订阅事件类型')).toBeInTheDocument();
    });
  });

  it('填写表单提交创建调用 post /webhooks', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /新建\s*Webhook/ }));
    });
    await waitFor(() => expect(screen.getByText('订阅事件类型')).toBeInTheDocument());

    // 名称
    fireEvent.change(screen.getByPlaceholderText('如: 告警回调'), {
      target: { value: '测试钩子' },
    });
    // 回调 URL（合法 URL 通过 type:url 校验）
    fireEvent.change(screen.getByPlaceholderText('https://example.com/webhook'), {
      target: { value: 'https://hook.example.com/cb' },
    });

    // antd 两字按钮自动插入空格: 创建 -> "创 建"
    const submitBtn = screen.getByRole('button', { name: /创\s*建/ });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith(
        '/webhooks',
        expect.objectContaining({
          name: '测试钩子',
          url: 'https://hook.example.com/cb',
        }),
      );
    });
  });

  it('删除 Webhook 触发 Popconfirm 后调用 delete API', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');

    const delBtn = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('.anticon-delete'));
    expect(delBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(delBtn!);
    });

    // Popconfirm 确认按钮: okText="删除" -> "删 除"（避开 description 文本中的"删除"）
    const confirmBtn = await screen.findByRole('button', { name: /删\s*除/ });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalledWith('/webhooks/1');
    });
  });

  it('测试发送调用 test API 并触发 message.loading', async () => {
    // test 接口解包路径 resp.data.data -> 投递结果对象
    mockApi.post.mockResolvedValue({
      data: { data: { status: 'success', status_code: 200, duration_ms: 50 } },
    });

    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');

    const testBtn = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('.anticon-thunderbolt'));
    expect(testBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(testBtn!);
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/webhooks/1/test');
    });
    expect(mockMessage.loading).toHaveBeenCalledWith('正在发送测试事件...', 0);
  });

  it('查看投递日志打开 Drawer 并调用 deliveries 接口', async () => {
    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });
    await screen.findByText('告警回调');

    const logBtn = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('.anticon-history'));
    expect(logBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(logBtn!);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/webhooks/1/deliveries',
        expect.objectContaining({ params: expect.objectContaining({ page: 1 }) }),
      );
    });
    expect(await screen.findByText(/投递日志/)).toBeInTheDocument();
  });
});

describe('Webhook 管理 — 边界条件', () => {
  it('空列表正常渲染', async () => {
    mockApi.get.mockResolvedValue({ data: { data: { items: [], total: 0 } } });

    await act(async () => {
      render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.queryByText('告警回调')).not.toBeInTheDocument();
    });
  });

  it('列表接口失败不崩溃并提示错误', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));

    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><WebhooksPage /></BrowserRouter>);
      container = c;
    });

    expect(container!).toBeTruthy();
    await waitFor(() => {
      expect(mockMessage.error).toHaveBeenCalled();
    });
  });
});
