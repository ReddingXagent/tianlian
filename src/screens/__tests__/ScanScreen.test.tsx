import { Alert } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import ScanScreen from '../ScanScreen';
import { scanApi } from '../../services/api';

jest.mock('../../services/api', () => ({
  scanApi: { scan: jest.fn(), checkIn: jest.fn() },
}));

const MOCK_RESULT = {
  type: 'device',
  id: 7,
  code: 'DEV-001',
  name: '充电桩01',
  status: 'online',
};

describe('ScanScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (scanApi.checkIn as jest.Mock).mockResolvedValue({
      data: { success: true, message: 'ok' },
    });
  });

  it('renders scanner frame and quick input buttons', () => {
    const { getByText, getByPlaceholderText } = render(<ScanScreen />);
    expect(getByPlaceholderText('输入设备/站点编码')).toBeTruthy();
    expect(getByText('DEV-001')).toBeTruthy();
    expect(getByText('STATION-A01')).toBeTruthy();
    expect(getByText('查询')).toBeTruthy();
  });

  it('shows error when code is empty', () => {
    const { getByText } = render(<ScanScreen />);
    fireEvent.press(getByText('查询'));
    expect(getByText('请输入设备/站点编码')).toBeTruthy();
  });

  it('fills the input via a quick input button', () => {
    const { getByText, getByPlaceholderText } = render(<ScanScreen />);
    fireEvent.press(getByText('STATION-A01'));
    expect(getByPlaceholderText('输入设备/站点编码').props.value).toBe(
      'STATION-A01'
    );
  });

  it('shows scan result on success', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_RESULT });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('扫码结果')).toBeTruthy();
    expect(await findByText('编码: DEV-001')).toBeTruthy();
    expect(await findByText('名称: 充电桩01')).toBeTruthy();
  });

  it('shows error message on scan failure', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue({
      response: { data: { message: '未找到设备' } },
    });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'XXX');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('未找到设备')).toBeTruthy();
  });

  it('prompts sign-in confirmation after a successful scan', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_RESULT });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('扫码签到'));
    expect(alertSpy).toHaveBeenCalledWith(
      '扫码签到',
      expect.stringContaining('签到'),
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });
});
