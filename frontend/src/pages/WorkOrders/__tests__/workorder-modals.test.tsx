/**
 * 工单生命周期补全组件测试 — 到场签到 / 申请支援 / 申请备件 / 验收评价（spec 2.2）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockWorkorderAPI } = vi.hoisted(() => ({
  mockWorkorderAPI: {
    checkin: vi.fn(),
    support: vi.fn(),
    requestParts: vi.fn(),
    rate: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  __esModule: true,
  workorderAPI: mockWorkorderAPI,
}));

import CheckInModal from '../components/CheckInModal';
import SupportModal from '../components/SupportModal';
import SparePartsModal from '../components/SparePartsModal';
import RatingModal from '../components/RatingModal';

beforeEach(() => {
  vi.clearAllMocks();
  mockWorkorderAPI.checkin.mockResolvedValue({ data: {} });
  mockWorkorderAPI.support.mockResolvedValue({ data: {} });
  mockWorkorderAPI.requestParts.mockResolvedValue({ data: {} });
  mockWorkorderAPI.rate.mockResolvedValue({ data: {} });
});

describe('CheckInModal 到场签到', () => {
  it('渲染标题与定位/提交按钮', () => {
    render(<CheckInModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('到场签到')).toBeInTheDocument();
    expect(screen.getByText('获取当前位置')).toBeInTheDocument();
    expect(screen.getByText('确认签到')).toBeInTheDocument();
  });

  it('点击定位按钮调用 geolocation', async () => {
    const getCurrentPosition = vi.fn((cb: (p: { coords: { latitude: number; longitude: number } }) => void) =>
      cb({ coords: { latitude: 31.2304, longitude: 121.4737 } }),
    );
    Object.defineProperty(global.navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true });
    render(<CheckInModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('获取当前位置'));
    await waitFor(() => expect(getCurrentPosition).toHaveBeenCalled());
  });

  it('提交签到调用 checkin API 并回调 onSuccess', async () => {
    const onSuccess = vi.fn();
    render(<CheckInModal open orderId="WO-9" onCancel={vi.fn()} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByPlaceholderText('请输入或确认到场地址'), { target: { value: '浦东站点' } });
    fireEvent.click(screen.getByText('确认签到'));
    await waitFor(() =>
      expect(mockWorkorderAPI.checkin).toHaveBeenCalledWith('WO-9', expect.objectContaining({ address: '浦东站点' })),
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });
});

describe('SupportModal 申请支援', () => {
  it('渲染标题与提交按钮', () => {
    render(<SupportModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('申请支援')).toBeInTheDocument();
    expect(screen.getByText('提交支援请求')).toBeInTheDocument();
  });

  it('校验必填：不填原因无法提交', async () => {
    render(<SupportModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('提交支援请求'));
    await waitFor(() => expect(screen.getByText('请说明需要支援的原因')).toBeInTheDocument());
    expect(mockWorkorderAPI.support).not.toHaveBeenCalled();
  });

  it('填写原因后提交调用 support API', async () => {
    render(<SupportModal open orderId="WO-7" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/疑难故障/), { target: { value: '需要高级工程师协助' } });
    fireEvent.click(screen.getByText('提交支援请求'));
    await waitFor(() =>
      expect(mockWorkorderAPI.support).toHaveBeenCalledWith('WO-7', expect.objectContaining({ reason: '需要高级工程师协助' })),
    );
  });
});

describe('SparePartsModal 申请备件', () => {
  it('渲染标题与提交按钮', () => {
    render(<SparePartsModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('申请备件')).toBeInTheDocument();
    expect(screen.getByText('提交备件申请')).toBeInTheDocument();
  });

  it('填写备件名与原因后提交调用 requestParts API（数量默认1）', async () => {
    render(<SparePartsModal open orderId="WO-8" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('如：交流接触器'), { target: { value: '交流接触器' } });
    fireEvent.change(screen.getByPlaceholderText(/线圈烧毁/), { target: { value: '原接触器损坏' } });
    fireEvent.click(screen.getByText('提交备件申请'));
    await waitFor(() =>
      expect(mockWorkorderAPI.requestParts).toHaveBeenCalledWith(
        'WO-8',
        expect.objectContaining({ part_name: '交流接触器', quantity: 1, reason: '原接触器损坏' }),
      ),
    );
  });
});

describe('RatingModal 验收评价', () => {
  it('渲染三维度评价标签', () => {
    render(<RatingModal open orderId="WO-1" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    expect(screen.getByText('验收评价')).toBeInTheDocument();
    expect(screen.getByText('响应速度')).toBeInTheDocument();
    expect(screen.getByText('维修质量')).toBeInTheDocument();
    expect(screen.getByText('服务态度')).toBeInTheDocument();
  });

  it('提交评价调用 rate API（默认三星各5分）', async () => {
    render(<RatingModal open orderId="WO-6" onCancel={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByText('提交评价并完成验收'));
    await waitFor(() =>
      expect(mockWorkorderAPI.rate).toHaveBeenCalledWith(
        'WO-6',
        expect.objectContaining({ response_rating: 5, quality_rating: 5, attitude_rating: 5 }),
      ),
    );
  });
});
