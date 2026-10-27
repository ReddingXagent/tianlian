/**
 * ScanScreen ext3 — name fallback + branch boost
 * Cover: L68/L77/L95 name || code fallback (name empty/null)
 */
import { render, fireEvent, act } from '@testing-library/react-native';
import ScanScreen from '../ScanScreen';
import { scanApi } from '../../services/api';
import { Alert } from 'react-native';

jest.mock('../../services/api', () => ({
  scanApi: { scan: jest.fn(), checkIn: jest.fn() },
}));

jest.spyOn(Alert, 'alert').mockImplementation(() => {});

describe('ScanScreen.ext3 — name fallback branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // L68/L77: lastResult.name empty → fallback to code in signIn alert
  it('handleSignIn: name empty → uses code in alert text', async () => {
    const deviceNoName = {
      type: 'device',
      id: 9,
      code: 'DEV-NO-NAME',
      name: '',
      status: 'online',
    };
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: deviceNoName });
    (scanApi.checkIn as jest.Mock).mockResolvedValue({});

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-NO-NAME');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });

    // Wait for result with buttons
    expect(await findByText('扫码签到')).toBeTruthy();

    // Press sign in button → Alert.alert called with code fallback
    await act(async () => {
      fireEvent.press(getByText('扫码签到'));
    });
    expect(Alert.alert).toHaveBeenCalledWith(
      '扫码签到',
      expect.stringContaining('DEV-NO-NAME'),
      expect.any(Array)
    );
  });

  // L95: handleReportFault name empty → code fallback
  it('handleReportFault: name empty → uses code in alert text', async () => {
    const deviceNoName = {
      type: 'device',
      id: 10,
      code: 'DEV-X',
      name: '',
      status: 'online',
    };
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: deviceNoName });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-X');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });

    expect(await findByText('报修')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('报修'));
    });
    expect(Alert.alert).toHaveBeenCalledWith(
      '报修',
      expect.stringContaining('DEV-X'),
      expect.any(Array)
    );
  });

  // L61/L91: handleSignIn/handleReportFault guard (!lastResult)
  // These are structurally unreachable via UI since buttons only render when lastResult exists.
  // Confirmed dead code — skipping to avoid brittle tests.
});
