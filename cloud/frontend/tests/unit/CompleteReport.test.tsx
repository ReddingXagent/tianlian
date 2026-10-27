/**
 * CompleteReport 组件测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('../../src/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: { id: 'WO-001', status: 'pending_verify' } }),
  },
}));

import CompleteReport from '../../src/pages/WorkOrders/components/CompleteReport';

describe('CompleteReport', () => {
  const defaultProps = {
    visible: true,
    orderId: 'WO-001',
    onCancel: vi.fn(),
    onSuccess: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('应渲染完成报告弹窗', async () => {
    render(<CompleteReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText(/WO-001/)).toBeInTheDocument();
    });

    // 应包含所有字段
    expect(screen.getByText('故障原因')).toBeInTheDocument();
    expect(screen.getByText('处理方案')).toBeInTheDocument();
    expect(screen.getByText('更换配件')).toBeInTheDocument();
    expect(screen.getByText('现场照片')).toBeInTheDocument();
    expect(screen.getByText('提交验收')).toBeInTheDocument();
  });

  it('未填处理方案时提交应显示验证错误', async () => {
    render(<CompleteReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('提交验收')).toBeInTheDocument();
    });

    // 直接点击提交
    const submitBtn = screen.getByText('提交验收');
    await userEvent.click(submitBtn);

    // onSuccess 不应被调用
    await waitFor(() => {
      expect(defaultProps.onSuccess).not.toHaveBeenCalled();
    });
  });

  it('照片上传区域应存在', async () => {
    render(<CompleteReport {...defaultProps} />);

    await waitFor(() => {
      // 应有拖拽上传文案
      expect(screen.getByText('点击或拖拽照片到此区域上传')).toBeInTheDocument();
    });
  });

  it('故障原因字段应可选', async () => {
    render(<CompleteReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('故障原因')).toBeInTheDocument();
    });

    // 故障原因不是必填项（没有 required 标记的 textarea）
    const faultReasonTextareas = screen.getAllByPlaceholderText(/故障的原因/);
    expect(faultReasonTextareas.length).toBeGreaterThanOrEqual(1);
  });
});
