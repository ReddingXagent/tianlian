import React from 'react';
import { render } from '@testing-library/react-native';
import StatusBadge from '../StatusBadge';

describe('StatusBadge', () => {
  it('renders online badge', () => {
    const { getByText } = render(<StatusBadge status="online" />);
    expect(getByText('在线')).toBeTruthy();
  });

  it('renders offline badge', () => {
    const { getByText } = render(<StatusBadge status="offline" />);
    expect(getByText('离线')).toBeTruthy();
  });

  it('renders charging badge', () => {
    const { getByText } = render(<StatusBadge status="charging" />);
    expect(getByText('充电中')).toBeTruthy();
  });

  it('renders idle badge', () => {
    const { getByText } = render(<StatusBadge status="idle" />);
    expect(getByText('空闲')).toBeTruthy();
  });

  it('renders fault badge', () => {
    const { getByText } = render(<StatusBadge status="fault" />);
    expect(getByText('故障')).toBeTruthy();
  });

  it('renders completed badge', () => {
    const { getByText } = render(<StatusBadge status="completed" />);
    expect(getByText('已完成')).toBeTruthy();
  });

  it('renders unpaid badge', () => {
    const { getByText } = render(<StatusBadge status="unpaid" />);
    expect(getByText('未支付')).toBeTruthy();
  });

  it('renders dc type badge', () => {
    const { getByText } = render(<StatusBadge status="dc" />);
    expect(getByText('直流')).toBeTruthy();
  });

  it('renders ac type badge', () => {
    const { getByText } = render(<StatusBadge status="ac" />);
    expect(getByText('交流')).toBeTruthy();
  });

  it('renders custom label', () => {
    const { getByText } = render(<StatusBadge status="online" label="自定义" />);
    expect(getByText('自定义')).toBeTruthy();
  });

  it('renders unknown status as-is', () => {
    const { getByText } = render(<StatusBadge status="unknown" />);
    expect(getByText('unknown')).toBeTruthy();
  });
});