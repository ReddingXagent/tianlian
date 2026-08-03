import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { Linking } from 'react-native';
import CameraScanner from '../CameraScanner';

// 捕获 CameraView props 以便模拟扫描回调; 权限状态可在用例间切换
const mockCameraProps: { current: Record<string, any> | null } = { current: null };
let mockPermission: { status: string; granted: boolean; canAskAgain: boolean } | null = {
  status: 'granted',
  granted: true,
  canAskAgain: true,
};
const mockRequestPermission = jest.fn();

jest.mock('expo-camera', () => ({
  CameraView: (props: Record<string, any>) => {
    mockCameraProps.current = props;
    return null;
  },
  useCameraPermissions: () => [mockPermission, mockRequestPermission],
}));

describe('CameraScanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCameraProps.current = null;
    mockPermission = { status: 'granted', granted: true, canAskAgain: true };
  });

  const renderScanner = (onScan = jest.fn(), onClose = jest.fn()) => ({
    ...render(<CameraScanner onScan={onScan} onClose={onClose} />),
    onScan,
    onClose,
  });

  it('renders camera preview and close button when permission granted', () => {
    const { getByTestId } = renderScanner();
    expect(getByTestId('camera-view')).toBeTruthy();
    expect(getByTestId('camera-close-btn')).toBeTruthy();
    expect(mockCameraProps.current?.facing).toBe('back');
  });

  it('calls onClose when close button pressed', () => {
    const { getByTestId, onClose } = renderScanner();
    fireEvent.press(getByTestId('camera-close-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('parses scanned QR and invokes onScan with charger code', () => {
    const { onScan } = renderScanner();
    mockCameraProps.current?.onBarcodeScanned({
      data: 'https://charge.tianlian.com/charger/CH-007',
    });
    expect(onScan).toHaveBeenCalledWith('CH-007');
  });

  it('ignores unparseable (empty) scan data', () => {
    const { onScan } = renderScanner();
    mockCameraProps.current?.onBarcodeScanned({ data: '   ' });
    expect(onScan).not.toHaveBeenCalled();
  });

  it('dedupes repeated scans of the same code within cooldown', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-08-04T00:00:00Z'));
    const { onScan } = renderScanner();

    mockCameraProps.current?.onBarcodeScanned({ data: 'CH-001' });
    mockCameraProps.current?.onBarcodeScanned({ data: 'CH-001' });
    expect(onScan).toHaveBeenCalledTimes(1);

    // 冷却窗口过后允许再次触发
    jest.setSystemTime(new Date('2026-08-04T00:00:03Z'));
    mockCameraProps.current?.onBarcodeScanned({ data: 'CH-001' });
    expect(onScan).toHaveBeenCalledTimes(2);
    jest.useRealTimers();
  });

  it('does not dedupe different codes', () => {
    const { onScan } = renderScanner();
    mockCameraProps.current?.onBarcodeScanned({ data: 'CH-001' });
    mockCameraProps.current?.onBarcodeScanned({ data: 'CH-002' });
    expect(onScan).toHaveBeenCalledTimes(2);
  });

  it('renders nothing while permission state is loading', () => {
    mockPermission = null;
    const { queryByTestId } = renderScanner();
    expect(queryByTestId('camera-view')).toBeNull();
    expect(queryByTestId('camera-permission-box')).toBeNull();
  });

  it('shows request button when permission not granted but askable', () => {
    mockPermission = { status: 'denied', granted: false, canAskAgain: true };
    const { getByTestId } = renderScanner();
    fireEvent.press(getByTestId('camera-request-btn'));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  });

  it('routes to system settings when permission permanently denied', () => {
    mockPermission = { status: 'denied', granted: false, canAskAgain: false };
    const openSettings = jest.spyOn(Linking, 'openSettings').mockImplementation();
    const { getByTestId } = renderScanner();
    fireEvent.press(getByTestId('camera-settings-btn'));
    expect(openSettings).toHaveBeenCalledTimes(1);
    openSettings.mockRestore();
  });

  it('cancels back via cancel button on permission box', () => {
    mockPermission = { status: 'denied', granted: false, canAskAgain: true };
    const { getByTestId, onClose } = renderScanner();
    fireEvent.press(getByTestId('camera-cancel-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
