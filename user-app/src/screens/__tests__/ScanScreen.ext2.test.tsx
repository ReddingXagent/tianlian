import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import ScanScreen from '../ScanScreen';

// ─── Mocks ────────────────────────────────────────────────

const mockReplace = jest.fn();
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: mockNavigate,
    replace: mockReplace,
  }),
}));

const mockStartCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ startCharging: mockStartCharging }),
}));

jest.mock('../../services/api', () => ({
  chargingApi: { scan: jest.fn() },
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');

const mockCameraProps: { current: Record<string, any> | null } = { current: null };
jest.mock('expo-camera', () => ({
  CameraView: (props: Record<string, any>) => {
    mockCameraProps.current = props;
    return null;
  },
  useCameraPermissions: () => [
    { status: 'granted', granted: true, canAskAgain: true },
    () => Promise.resolve({ status: 'granted', granted: true, canAskAgain: true }),
  ],
}));

// ─── Helpers ───────────────────────────────────────────────

const renderScreen = () =>
  render(
    <SafeAreaProvider>
      <ScanScreen />
    </SafeAreaProvider>,
  );

describe('ScanScreen.ext2 — quick input button coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCameraProps.current = null;
  });

  // Line 169: press CH-001 quick input button
  it('CH-001 quick input button sets code value', () => {
    const { getByText, getByPlaceholderText } = renderScreen();
    fireEvent.press(getByText('CH-001'));
    expect(getByPlaceholderText('输入充电桩编码').props.value).toBe('CH-001');
  });

  // Line 181: press CH-003 quick input button
  it('CH-003 quick input button sets code value', () => {
    const { getByText, getByPlaceholderText } = renderScreen();
    fireEvent.press(getByText('CH-003'));
    expect(getByPlaceholderText('输入充电桩编码').props.value).toBe('CH-003');
  });

  // Lines 57-58: handleScan with empty input
  it('shows error when scanning with empty code', () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText } = renderScreen();
    // Press query button without entering code
    fireEvent.press(getByText('查询'));
    // The error state should be set (rendered in UI, not Alert)
    // handleScan uses setError, so check the rendered error text
    expect(getByText('请输入充电桩编码')).toBeTruthy();
    spy.mockRestore();
  });
});
