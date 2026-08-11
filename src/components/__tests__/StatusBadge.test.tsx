import React from 'react';
import { render } from '@testing-library/react-native';
import StatusBadge from '../StatusBadge';
import type { StatusType } from '../StatusBadge';

describe('StatusBadge', () => {
  it('should render with default label for online status', () => {
    const { getByText } = render(<StatusBadge status="online" />);
    const badgeText = getByText('在线');
    expect(badgeText).toBeTruthy();
    // 绿色背景 + 深绿色文字
    expect(badgeText.props.style).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ color: '#2e7d32' }),
      ])
    );
  });

  it('should render with default label for offline status', () => {
    const { getByText } = render(<StatusBadge status="offline" />);
    const badgeText = getByText('离线');
    expect(badgeText).toBeTruthy();
    expect(badgeText.props.style).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ color: '#c62828' }),
      ])
    );
  });

  it('should render with default label for fault status', () => {
    const { getByText } = render(<StatusBadge status="fault" />);
    const badgeText = getByText('故障');
    expect(badgeText).toBeTruthy();
  });

  it('should render with default label for maintenance status', () => {
    const { getByText } = render(<StatusBadge status="maintenance" />);
    const badgeText = getByText('维护');
    expect(badgeText).toBeTruthy();
  });

  it('should render with custom label when provided', () => {
    const { getByText } = render(<StatusBadge status="online" label="自定义在线" />);
    const badgeText = getByText('自定义在线');
    expect(badgeText).toBeTruthy();
  });

  it('should render all alarm status variants', () => {
    const alarmStatuses = [
      { status: 'unhandled' as const, label: '未处理', color: '#c62828' },
      { status: 'processing' as const, label: '处理中', color: '#f57f17' },
      { status: 'resolved' as const, label: '已解决', color: '#2e7d32' },
    ];

    alarmStatuses.forEach(({ status, label, color }) => {
      const { getByText, unmount } = render(<StatusBadge status={status} />);
      const badgeText = getByText(label);
      expect(badgeText).toBeTruthy();
      expect(badgeText.props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ color }),
        ])
      );
      unmount();
    });
  });

  it('should render all work order status variants', () => {
    const workOrderStatuses = [
      { status: 'pending' as const, label: '待处理', color: '#f57f17' },
      { status: 'in_progress' as const, label: '进行中', color: '#1565c0' },
      { status: 'completed' as const, label: '已完成', color: '#2e7d32' },
      { status: 'cancelled' as const, label: '已取消', color: '#616161' },
    ];

    workOrderStatuses.forEach(({ status, label, color }) => {
      const { getByText, unmount } = render(<StatusBadge status={status} />);
      const badgeText = getByText(label);
      expect(badgeText).toBeTruthy();
      expect(badgeText.props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ color }),
        ])
      );
      unmount();
    });
  });

  it('should render all priority variants', () => {
    const priorities = [
      { status: 'high' as const, label: '高', color: '#c62828' },
      { status: 'normal' as const, label: '中', color: '#1565c0' },
      { status: 'low' as const, label: '低', color: '#2e7d32' },
      { status: 'urgent' as const, label: '紧急', color: '#b71c1c' },
    ];

    priorities.forEach(({ status, label, color }) => {
      const { getByText, unmount } = render(<StatusBadge status={status} />);
      const badgeText = getByText(label);
      expect(badgeText).toBeTruthy();
      expect(badgeText.props.style).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ color }),
        ])
      );
      unmount();
    });
  });

  it('should render warning and critical status', () => {
    const { getByText: getWarningText } = render(<StatusBadge status="warning" />);
    expect(getWarningText('警告')).toBeTruthy();

    const { getByText: getCriticalText } = render(<StatusBadge status="critical" />);
    expect(getCriticalText('严重')).toBeTruthy();
  });

  it('should render info status', () => {
    const { getByText } = render(<StatusBadge status="info" />);
    expect(getByText('信息')).toBeTruthy();
  });

  it('should render unknown status with fallback', () => {
    const { getByText } = render(<StatusBadge status={"unknown" as unknown as StatusType} />);
    expect(getByText('unknown')).toBeTruthy();
  });
});