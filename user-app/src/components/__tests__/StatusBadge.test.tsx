import React from 'react';
import { render } from '@testing-library/react-native';
import * as RN from 'react-native';
import StatusBadge from '../StatusBadge';
import { colorsDark, colorsLight } from '../../theme/colors';

describe('StatusBadge', () => {
  let colorSchemeSpy: jest.SpyInstance;

  beforeEach(() => {
    colorSchemeSpy = jest.spyOn(RN, 'useColorScheme').mockReturnValue('light');
  });

  afterEach(() => {
    colorSchemeSpy.mockRestore();
  });

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

  it('light mode: online badge uses semantic success pair', () => {
    const { UNSAFE_getByType } = render(<StatusBadge status="online" />);
    const badge = UNSAFE_getByType(RN.View);
    const text = UNSAFE_getByType(RN.Text);
    expect(badge.props.style.some((s: Record<string, string>) => s.backgroundColor === colorsLight.successBg)).toBe(true);
    expect(text.props.style.some((s: Record<string, string>) => s.color === colorsLight.success)).toBe(true);
  });

  it('dark mode: online badge colors flip with theme', () => {
    colorSchemeSpy.mockReturnValue('dark');
    const { UNSAFE_getByType } = render(<StatusBadge status="online" />);
    const badge = UNSAFE_getByType(RN.View);
    const text = UNSAFE_getByType(RN.Text);
    expect(badge.props.style.some((s: Record<string, string>) => s.backgroundColor === colorsDark.successBg)).toBe(true);
    expect(text.props.style.some((s: Record<string, string>) => s.color === colorsDark.success)).toBe(true);
    expect(badge.props.style.some((s: Record<string, string>) => s.backgroundColor === colorsLight.successBg)).toBe(false);
  });

  it('dark mode: ac badge uses purple pair and flips in dark', () => {
    colorSchemeSpy.mockReturnValue('dark');
    const { UNSAFE_getByType } = render(<StatusBadge status="ac" />);
    const badge = UNSAFE_getByType(RN.View);
    const text = UNSAFE_getByType(RN.Text);
    expect(badge.props.style.some((s: Record<string, string>) => s.backgroundColor === colorsDark.purpleBg)).toBe(true);
    expect(text.props.style.some((s: Record<string, string>) => s.color === colorsDark.purple)).toBe(true);
  });

  it('unknown status falls back to neutral pair (theme-aware)', () => {
    colorSchemeSpy.mockReturnValue('dark');
    const { UNSAFE_getByType } = render(<StatusBadge status="mystery" />);
    const badge = UNSAFE_getByType(RN.View);
    const text = UNSAFE_getByType(RN.Text);
    expect(badge.props.style.some((s: Record<string, string>) => s.backgroundColor === colorsDark.neutralBg)).toBe(true);
    expect(text.props.style.some((s: Record<string, string>) => s.color === colorsDark.neutralText)).toBe(true);
  });
});