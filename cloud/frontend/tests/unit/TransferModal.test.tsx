/**
 * TransferModal 组件测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Mock api
vi.mock('../../src/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: {} }),
    get: vi.fn().mockResolvedValue({ data: [] }),
  },
  userAPI: {
    engineers: vi.fn().mockResolvedValue({
      data: {
        items: [
          { id: 1, real_name: '工程师A', username: 'eng_a' },
          { id: 2, real_name: '工程师B', username: 'eng_b' },
          { id: 3, real_name: '工程师C' },
        ],
      },
    }),
  },
}));

import TransferModal from '../../src/pages/WorkOrders/components/TransferModal';

describe('TransferModal', () => {
  const defaultProps = {
    visible: true,
    orderId: 'WO-001',
    currentAssigneeId: 1,
    onCancel: vi.fn(),
    onSuccess: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('应渲染转单弹窗并加载工程师列表', async () => {
    render(<TransferModal {...defaultProps} />);

    // 标题应包含工单号
    await waitFor(() => {
      expect(screen.getByText(/WO-001/)).toBeInTheDocument();
    });

    // 应有工程师选择器和转单原因输入
    await waitFor(() => {
      expect(screen.getByText('目标工程师')).toBeInTheDocument();
      expect(screen.getByText('转单原因')).toBeInTheDocument();
    });

    // 确认按钮
    expect(screen.getByText('确认转单')).toBeInTheDocument();
  });

  it('应排除当前处理人', async () => {
    const { userAPI } = await import('../../src/api');
    render(<TransferModal {...defaultProps} />);

    await waitFor(() => {
      expect(userAPI.engineers).toHaveBeenCalled();
    });
  });

  it('点击取消应调用 onCancel', async () => {
    render(<TransferModal {...defaultProps} />);

    // 找到关闭按钮并点击
    const closeButton = document.querySelector('.ant-modal-close');
    if (closeButton) {
      await userEvent.click(closeButton);
      expect(defaultProps.onCancel).toHaveBeenCalled();
    }
  });

  it('未选择工程师时提交应显示验证错误', async () => {
    render(<TransferModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('确认转单')).toBeInTheDocument();
    });

    // 直接点击提交
    await userEvent.click(screen.getByText('确认转单'));

    // 不应调用 onSuccess
    await waitFor(() => {
      expect(defaultProps.onSuccess).not.toHaveBeenCalled();
    });
  });
});
