/**
 * 知识库编辑页 — 保存路径纵深防御净化测试 (卡 6061eb1a / GHSA-v3m3-f69x-jf25)
 *
 * 背景：quill@2.0.3 的 HTML export 存在 XSS 漏洞。本项目的「主防线」是渲染层
 * DOMPurify（见 Detail.tsx / SearchTab.tsx 与 knowledge.xss.test.tsx，已覆盖）。
 * 此测试锁定「第二道防线」——保存路径同样净化 content，确保写入后端的 HTML 不含
 * 可执行脚本，保护规划中的 mobile 端等未来消费者（它们可能不在渲染层二次净化）。
 *
 * 通过将 react-quill-new mock 为受控 textarea 来驱动 onChange（content 状态），
 * 规避 jsdom 下真实 Quill 的 Selection API 依赖与 flakiness。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock react-quill-new —— 受控 textarea 驱动 content 状态
// ═══════════════════════════════════════════
vi.mock('react-quill-new', () => {
  const MockQuill = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea
      data-testid="quill-editor"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
  return { default: MockQuill };
});

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockKnowledgeAPI } = vi.hoisted(() => ({
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
}));

vi.mock('../../../api', () => ({
  knowledgeAPI: mockKnowledgeAPI,
}));

// 保留真实 antd 组件（Form/Input/Select/Button 需真实渲染与校验），仅 mock message
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import KnowledgeEdit from '../Edit';

// ═══════════════════════════════════════════
// 公共 setup
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockKnowledgeAPI.categories.mockResolvedValue({ data: ['维修指南', '故障诊断'] });
  mockKnowledgeAPI.create.mockResolvedValue({ data: { id: 42 } });
  mockKnowledgeAPI.update.mockResolvedValue({ data: { id: 1 } });
});

const XSS_PAYLOAD = [
  '<p>正常内容：逆变器安全操作规范</p>',
  "<script>alert('xss-script')</script>",
  '<img src="x" onerror="alert(\'xss-img\')" alt="恶意图">',
  '<img src="legit.png" alt="合法图">',
].join('');

// ═══════════════════════════════════════════
// 创建路径 —— knowledgeAPI.create
// ═══════════════════════════════════════════
describe('知识库 Edit — 保存路径净化 (create)', () => {
  it('提交时剥离 content 中 <script> 与 <img onerror>，保留正常富文本', async () => {
    // 无 :id 路由 → 创建模式
    render(
      <MemoryRouter>
        <KnowledgeEdit />
      </MemoryRouter>
    );

    // 填标题（category 由 initialValues 预置，校验可过）
    fireEvent.change(screen.getByPlaceholderText('请输入文章标题'), {
      target: { value: '逆变器安全规范' },
    });

    // 驱动富文本 content 状态注入 XSS payload
    fireEvent.change(screen.getByTestId('quill-editor'), {
      target: { value: XSS_PAYLOAD },
    });

    // 提交
    fireEvent.click(screen.getByRole('button', { name: /保存/ }));

    await waitFor(() => {
      expect(mockKnowledgeAPI.create).toHaveBeenCalledTimes(1);
    });

    const payload = mockKnowledgeAPI.create.mock.calls[0][0] as { content: string };

    // 正向锚点：正常富文本保留（证明净化未吞掉合法内容）
    expect(payload.content).toContain('正常内容');
    expect(payload.content).toContain('逆变器安全操作规范');

    // <script> 与 onerror 必须被剥离
    expect(payload.content).not.toContain('<script>');
    expect(payload.content).not.toMatch(/onerror/i);
    // 合法 <img> 不被误杀
    expect(payload.content).toContain('legit.png');
  });
});

// ═══════════════════════════════════════════
// 更新路径 —— knowledgeAPI.update
// ═══════════════════════════════════════════
describe('知识库 Edit — 保存路径净化 (update)', () => {
  it('更新提交时同样剥离 content 中可执行脚本', async () => {
    // :id 路由 → 编辑模式；get 回灌初始数据
    mockKnowledgeAPI.get.mockResolvedValue({
      data: { id: 1, title: '原标题', category: '维修指南', content: '<p>旧内容</p>', tags: '' },
    });

    render(
      <MemoryRouter initialEntries={['/edit/1']}>
        <Routes>
          <Route path="/edit/:id" element={<KnowledgeEdit />} />
        </Routes>
      </MemoryRouter>
    );

    // 等 get 回灌完成、编辑器出现
    await waitFor(() => {
      expect(screen.getByTestId('quill-editor')).toBeInTheDocument();
    });

    // 覆盖 content 为 XSS payload
    fireEvent.change(screen.getByTestId('quill-editor'), {
      target: { value: XSS_PAYLOAD },
    });

    fireEvent.click(screen.getByRole('button', { name: /保存/ }));

    await waitFor(() => {
      expect(mockKnowledgeAPI.update).toHaveBeenCalledTimes(1);
    });

    const payload = mockKnowledgeAPI.update.mock.calls[0][1] as { content: string };

    expect(payload.content).toContain('正常内容');
    expect(payload.content).not.toContain('<script>');
    expect(payload.content).not.toMatch(/onerror/i);
  });
});
