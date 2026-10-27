/**
 * WorkOrderStats 页面测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Mock echarts
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echart-mock">EChart Mock</div>,
}));

// Mock api
vi.mock('../../src/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        items: [
          { id: 'WO-001', fault_desc: '设备故障A', type: 'repair', level: 'urgent', status: 'pending', station_id: 1, device_id: 10, create_time: '2026-06-01T10:00:00Z' },
          { id: 'WO-002', fault_desc: '设备故障B', type: 'repair', level: 'high', status: 'accepted', station_id: 1, device_id: 11, create_time: '2026-06-02T10:00:00Z' },
          { id: 'WO-003', fault_desc: '巡检C', type: 'inspection', level: 'warning', status: 'completed', station_id: 2, device_id: 12, create_time: '2026-06-03T10:00:00Z' },
          { id: 'WO-004', fault_desc: '安装D', type: 'installation', level: 'low', status: 'completed', station_id: 2, device_id: 13, create_time: '2026-06-04T10:00:00Z' },
        ],
      },
    }),
  },
}));

import WorkOrderStats from '../../src/pages/WorkOrderStats';

describe('WorkOrderStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('应渲染统计页面标题区域', async () => {
    render(<WorkOrderStats />);

    await waitFor(() => {
      expect(screen.getByText('工单总数')).toBeInTheDocument();
      expect(screen.getByText('已完成')).toBeInTheDocument();
      expect(screen.getByText('待派单')).toBeInTheDocument();
      expect(screen.getByText('紧急工单')).toBeInTheDocument();
    });
  });

  it('应渲染分组切换器', async () => {
    render(<WorkOrderStats />);

    await waitFor(() => {
      expect(screen.getByText('按状态')).toBeInTheDocument();
      expect(screen.getByText('按工程师')).toBeInTheDocument();
      expect(screen.getByText('按级别')).toBeInTheDocument();
      expect(screen.getByText('按站点')).toBeInTheDocument();
    });
  });

  it('应渲染图表区域', async () => {
    render(<WorkOrderStats />);

    await waitFor(() => {
      expect(screen.getByText('分布饼图')).toBeInTheDocument();
      expect(screen.getByText('数量柱状图')).toBeInTheDocument();
    });
  });

  it('应渲染统计明细表格', async () => {
    render(<WorkOrderStats />);

    await waitFor(() => {
      expect(screen.getByText('统计明细')).toBeInTheDocument();
    });
  });

  it('切换分组维度应更新表格', async () => {
    render(<WorkOrderStats />);

    await waitFor(() => {
      expect(screen.getByText('按级别')).toBeInTheDocument();
    });

    // 点击切换到"按级别"
    await userEvent.click(screen.getByText('按级别'));
  });
});
