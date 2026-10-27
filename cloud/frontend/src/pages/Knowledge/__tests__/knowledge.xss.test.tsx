/**
 * 知识库 — 存储型 XSS 净化测试（卡 0160e45e）
 *
 * 验证渲染用户可控富文本前经 DOMPurify 净化：
 *  - <script> 标签被剥离（不进入 DOM）
 *  - <img onerror=...> 的 onerror 事件处理器被剥离
 *  - 正常富文本（<p>、合法 <img>、<mark> 高亮）不被破坏
 *
 * 每个用例先断言「正常内容已渲染」作为正向锚点，证明渲染确实发生，
 * 避免因渲染未触发导致的「假通过」。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom';
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

// 保留真实 antd 组件（List/Card 等需真实渲染以便断言 DOM），仅 mock message
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import KnowledgeDetail from '../Detail';
import Knowledge from '../index';

// ═══════════════════════════════════════════
// 公共 setup
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  // Knowledge 挂载时的基础数据，避免空 mock 抛错
  mockKnowledgeAPI.list.mockResolvedValue({ data: { items: [], total: 0 } });
  mockKnowledgeAPI.categories.mockResolvedValue({ data: [] });
  mockKnowledgeAPI.stats.mockResolvedValue({ data: { total: 0, categories: 0, total_views: 0 } });
  mockFaqAPI.list.mockResolvedValue({ data: [] });
  mockFaqAPI.categories.mockResolvedValue({ data: [] });
});

// ═══════════════════════════════════════════
// Detail — article.content 渲染点
// ═══════════════════════════════════════════
describe('知识库 Detail — 存储型 XSS 净化 (article.content)', () => {
  it('剥离 <script> 与 <img onerror>，保留正常富文本', async () => {
    const xssContent = [
      '<p>正常内容：逆变器安全操作规范</p>',
      "<script>alert('xss-script')</script>",
      '<img src="x" onerror="alert(\'xss-img\')" alt="恶意图">',
      '<img src="legit.png" alt="合法图">',
    ].join('');

    mockKnowledgeAPI.get.mockResolvedValue({
      data: {
        id: 1,
        title: '逆变器安全规范',
        category: '维修指南',
        content: xssContent,
        created_at: '2025-06-01T00:00:00Z',
      },
    });

    // Detail 依赖 useParams().id，必须挂在匹配 :id 的路由下，否则不触发 fetchArticle
    const utils = render(
      <MemoryRouter initialEntries={['/detail/1']}>
        <Routes>
          <Route path="/detail/:id" element={<KnowledgeDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // 正向锚点：正常段落已渲染（证明 dangerouslySetInnerHTML 确实执行）
    await waitFor(() => {
      expect(screen.getByText(/逆变器安全操作规范/)).toBeInTheDocument();
    });

    // <script> 必须被剥离，不进入 DOM
    expect(utils.container.querySelector('script')).toBeNull();

    // 所有 <img> 不得携带 onerror 事件处理器
    const imgs = utils.container.querySelectorAll('img');
    expect(imgs.length).toBeGreaterThan(0);
    imgs.forEach((img) => {
      expect(img.getAttribute('onerror')).toBeNull();
    });

    // 合法 <img> 不被误杀
    expect(utils.container.querySelector('img[alt="合法图"]')).not.toBeNull();
  });
});

// ═══════════════════════════════════════════
// 搜索高亮 — summary/highlight 渲染点
// ═══════════════════════════════════════════
describe('知识库 搜索高亮 — 存储型 XSS 净化 (summary/highlight)', () => {
  it('剥离 summary 中 <img onerror>，保留 <mark> 高亮替换', async () => {
    mockKnowledgeAPI.search.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            title: '逆变器指南',
            category: '维修指南',
            summary: '<mark>逆变器</mark>关键说明<img src="x" onerror="alert(\'xss\')">',
            author: '张工',
            updated_at: '2025-06-05T00:00:00Z',
          },
        ],
      },
    });

    const utils = render(<BrowserRouter><Knowledge /></BrowserRouter>);

    // 等 Tabs 渲染就绪（list/分类/统计 effect 完成后再交互）
    await waitFor(() => expect(screen.getByText('搜索')).toBeInTheDocument());

    // 切到搜索 Tab
    await act(async () => {
      fireEvent.click(screen.getByText('搜索'));
    });

    // 输入关键词并触发 onSearch
    const input = screen.getByPlaceholderText('搜索知识库文章（标题/内容）…') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { value: '逆变器' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', charCode: 13 });
    });

    // 正向锚点：搜索已调用且高亮文本进入 DOM（证明第 975 行渲染发生）
    await waitFor(() => {
      expect(mockKnowledgeAPI.search).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(utils.container.textContent).toMatch(/逆变器/);
    });

    // <img onerror> 必须被剥离
    const badImgs = utils.container.querySelectorAll('img[onerror]');
    expect(badImgs.length).toBe(0);

    // <mark> 被替换为 <span style=...> 高亮，确认未破坏高亮逻辑
    const highlight = utils.container.querySelector('span[style*="fff3b0"]');
    expect(highlight).not.toBeNull();
    expect(highlight?.textContent).toContain('逆变器');
  });
});
