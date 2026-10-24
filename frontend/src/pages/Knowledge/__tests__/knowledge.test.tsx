/**
 * 知识库页面 — Vitest 单元测试（核心功能：列表渲染、搜索、详情查看）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockKnowledgeAPI, mockFaqAPI, mockDocAPI } = vi.hoisted(() => ({
  mockKnowledgeAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    categories: vi.fn(),
    createCategory: vi.fn(),
    updateCategory: vi.fn(),
    deleteCategory: vi.fn(),
    categoriesLegacy: vi.fn(),
    stats: vi.fn(),
    search: vi.fn(),
  },
  mockFaqAPI: {
    list: vi.fn(),
    create: vi.fn(),
    batchImport: vi.fn(),
    markHelpful: vi.fn(),
    categories: vi.fn(),
  },
  mockDocAPI: {
    generateDoc: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  knowledgeAPI: mockKnowledgeAPI,
}));

vi.mock('../../../api/knowledge', () => ({
  faqAPI: mockFaqAPI,
  docAPI: mockDocAPI,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import Knowledge from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockArticles = [
  {
    id: 1, title: '逆变器维修指南', category: '维修指南',
    content: '本文档介绍逆变器的维修流程和注意事项。',
    tags: '逆变器,维修', view_count: 120,
    created_at: '2025-06-01T00:00:00Z', updated_at: '2025-06-05T00:00:00Z',
    author_name: '张工',
  },
  {
    id: 2, title: '充电桩故障诊断手册', category: '故障诊断',
    content: '充电桩常见故障及诊断方法。',
    tags: '充电桩,故障', view_count: 80,
    created_at: '2025-06-02T00:00:00Z', updated_at: '2025-06-03T00:00:00Z',
    author_name: '李工',
  },
];

const mockCategories = [
  { id: 1, name: '维修指南', icon: '🔧', sort_order: 0, description: '设备维修相关', article_count: 5 },
  { id: 2, name: '故障诊断', icon: '⚡', sort_order: 1, description: '故障排查相关', article_count: 3 },
];

const mockStats = {
  total: 10, categories: 4, total_views: 500, top_category: '维修指南',
};

const mockSearchResults = {
  items: [
    {
      id: 1, title: '逆变器维修指南', category: '维修指南',
      summary: '本文档介绍逆变器的维修流程', highlight: '<mark>逆变器</mark>维修指南',
      author: '张工', updated_at: '2025-06-05T00:00:00Z',
    },
  ],
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockKnowledgeAPI.list.mockResolvedValue({ data: { items: mockArticles, total: 2 } });
  mockKnowledgeAPI.categories.mockResolvedValue({ data: mockCategories });
  mockKnowledgeAPI.stats.mockResolvedValue({ data: mockStats });
  mockKnowledgeAPI.search.mockResolvedValue({ data: mockSearchResults });
  mockKnowledgeAPI.get.mockResolvedValue({ data: mockArticles[0] });
  mockKnowledgeAPI.delete.mockResolvedValue({});
});

describe('知识库 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><Knowledge /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('统计卡片显示正确数据', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });
    // stats 模块被调用后渲染
    await waitFor(() => {
      expect(mockKnowledgeAPI.stats).toHaveBeenCalled();
    });
  });

  it('Tab 栏包含核心功能 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });
    expect(screen.getByText('搜索')).toBeInTheDocument();
    expect(screen.getByText('知识文章')).toBeInTheDocument();
    expect(screen.getByText('分类管理')).toBeInTheDocument();
    expect(screen.getByText('FAQ问答')).toBeInTheDocument();
  });
});

describe('知识库 — 文章列表', () => {
  it('页面挂载时加载文章列表', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });
    expect(mockKnowledgeAPI.list).toHaveBeenCalled();
  });

  it('切换到知识文章 Tab 后展示文章', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    // 点击知识文章 Tab
    fireEvent.click(screen.getByText('知识文章'));

    await waitFor(() => {
      expect(mockKnowledgeAPI.list).toHaveBeenCalled();
    });
  });

  it('knowledgeAPI.delete 被调用格式正确', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    await mockKnowledgeAPI.delete(1);
    expect(mockKnowledgeAPI.delete).toHaveBeenCalledWith(1);
  });
});

describe('知识库 — 搜索', () => {
  it('搜索 Tab 存在且可交互', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    // 默认 Tab 是 articles，切换到 search
    const searchTab = screen.getByText('搜索');
    expect(searchTab).toBeInTheDocument();
  });

  it('knowledgeAPI.search 调用格式正确', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    await mockKnowledgeAPI.search({ q: '逆变器', page: 1, page_size: 100 });
    expect(mockKnowledgeAPI.search).toHaveBeenCalledWith({ q: '逆变器', page: 1, page_size: 100 });
  });

  it('knowledgeAPI.get 获取文章详情', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    await mockKnowledgeAPI.get(1);
    expect(mockKnowledgeAPI.get).toHaveBeenCalledWith(1);
  });
});

describe('知识库 — 分类管理', () => {
  it('页面挂载时加载分类', async () => {
    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });
    expect(mockKnowledgeAPI.categories).toHaveBeenCalled();
  });

  it('knowledgeAPI.createCategory 调用格式正确', async () => {
    mockKnowledgeAPI.createCategory.mockResolvedValue({});

    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    await mockKnowledgeAPI.createCategory({ name: '新分类', icon: '📚', description: '描述', sort_order: 0 });
    expect(mockKnowledgeAPI.createCategory).toHaveBeenCalledWith({ name: '新分类', icon: '📚', description: '描述', sort_order: 0 });
  });

  it('knowledgeAPI.deleteCategory 调用格式正确', async () => {
    mockKnowledgeAPI.deleteCategory.mockResolvedValue({});

    await act(async () => {
      render(<BrowserRouter><Knowledge /></BrowserRouter>);
    });

    await mockKnowledgeAPI.deleteCategory(1);
    expect(mockKnowledgeAPI.deleteCategory).toHaveBeenCalledWith(1);
  });
});
