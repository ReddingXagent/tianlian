/**
 * 巡检模板 / 结果录入组件测试（spec 2.5）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockInspectionAPI } = vi.hoisted(() => ({
  mockInspectionAPI: {
    templates: { create: vi.fn(), update: vi.fn(), delete: vi.fn() },
    results: { create: vi.fn() },
  },
}));

vi.mock('../../../api', () => ({
  __esModule: true,
  inspectionAPI: mockInspectionAPI,
}));

import TemplateModal from '../components/TemplateModal';
import ResultRecordModal from '../components/ResultRecordModal';

beforeEach(() => {
  vi.clearAllMocks();
  mockInspectionAPI.templates.create.mockResolvedValue({ data: {} });
  mockInspectionAPI.templates.update.mockResolvedValue({ data: {} });
  mockInspectionAPI.results.create.mockResolvedValue({ data: {} });
});

describe('TemplateModal 巡检模板', () => {
  it('渲染新建模板标题', () => {
    render(<TemplateModal open editing={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('新建巡检模板')).toBeInTheDocument();
  });

  it('不填模板名无法提交', async () => {
    render(<TemplateModal open editing={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('保存模板'));
    await waitFor(() => expect(screen.getByText('请输入模板名称')).toBeInTheDocument());
    expect(mockInspectionAPI.templates.create).not.toHaveBeenCalled();
  });

  it('填写模板名后提交调用 templates.create（空巡检项被过滤）', async () => {
    render(<TemplateModal open editing={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('如：充电桩周巡检模板'), { target: { value: '充电桩周检' } });
    fireEvent.click(screen.getByText('保存模板'));
    await waitFor(() =>
      expect(mockInspectionAPI.templates.create).toHaveBeenCalledWith(
        expect.objectContaining({ name: '充电桩周检', target: 'all', items: [] }),
      ),
    );
  });
});

describe('ResultRecordModal 巡检结果录入', () => {
  it('渲染结果录入标题', () => {
    render(<ResultRecordModal open taskId={1} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('巡检结果录入')).toBeInTheDocument();
  });

  it('录入一项结果后提交调用 results.create', async () => {
    render(<ResultRecordModal open taskId={7} taskName="浦东周检" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('巡检项'), { target: { value: '外观' } });
    fireEvent.change(screen.getByPlaceholderText('实测值'), { target: { value: '正常' } });
    fireEvent.click(screen.getByText('保存巡检结果'));
    await waitFor(() =>
      expect(mockInspectionAPI.results.create).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ results: expect.arrayContaining([expect.objectContaining({ item_name: '外观' })]) }),
      ),
    );
  });

  it('未选任务时不提交', async () => {
    render(<ResultRecordModal open taskId={null} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('保存巡检结果'));
    await waitFor(() => expect(mockInspectionAPI.results.create).not.toHaveBeenCalled());
  });
});
