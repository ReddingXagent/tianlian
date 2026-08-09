/**
 * ScanScreen ext4 — uncovered branches: line 77 name||code in signIn, line 91 handleReportFault
 */
import { Alert } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import ScanScreen from '../ScanScreen';
import { scanApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  scanApi: {
    scan: jest.fn(),
    checkIn: jest.fn(),
  },
}));

const MOCK_RESULT_NO_NAME = {
  id: 1, code: 'DEV-001', name: '', type: 'charger',
  station: '站A', status: 'online',
};

const MOCK_RESULT_FULL = {
  id: 2, code: 'DEV-002', name: '充电桩二号', type: 'station',
  station: '站B', status: 'idle',
};

describe('ScanScreen.ext4 branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  // Line 77: name||code — signIn when name is empty, alert shows code
  it('signIn alert shows code when name is empty', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_RESULT_NO_NAME });
    const { getByPlaceholderText, getByText } = render(<ScanScreen />);

    // Scan first
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    fireEvent.press(getByText('查询'));

    // Wait for result to render
    await waitFor(() => {
      expect(getByText('扫码结果')).toBeTruthy();
    });

    // Press 签到 button
    fireEvent.press(getByText('扫码签到'));

    expect(Alert.alert).toHaveBeenCalledWith(
      '扫码签到',
      expect.stringContaining('DEV-001'),
      expect.any(Array),
    );
  });

  // Line 91: handleReportFault shows alert
  it('reportFault shows alert with device name', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_RESULT_FULL });
    const { getByPlaceholderText, getByText } = render(<ScanScreen />);

    // Scan first
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-002');
    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('扫码结果')).toBeTruthy();
    });

    // Press 报修 button
    fireEvent.press(getByText('报修'));

    expect(Alert.alert).toHaveBeenCalledWith(
      '报修',
      expect.stringContaining('充电桩二号'),
      expect.any(Array),
    );
  });
});
