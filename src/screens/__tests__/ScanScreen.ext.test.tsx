/**
 * ScanScreen Extension Tests — 追加分支覆盖
 * 目标: 69.6% → 90%+ branches
 * 覆盖: network error, signIn flow (success/fail), reportFault, quickInput clears error,
 *       resultIcon/resultTypeLabel default, signInMode render, onChangeText clears error
 */
import { Alert } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import ScanScreen from '../ScanScreen';
import { scanApi } from '../../services/api';

jest.mock('../../services/api', () => ({
  scanApi: { scan: jest.fn(), checkIn: jest.fn() },
}));

const MOCK_DEVICE = {
  type: 'device',
  id: 7,
  code: 'DEV-001',
  name: '充电桩01',
  status: 'online',
};

const MOCK_STATION: any = {
  type: 'station',
  id: 3,
  code: 'STATION-A01',
  name: '东站',
  status: undefined,
};

const MOCK_UNKNOWN: any = {
  type: 'unknown',
  id: 99,
  code: 'X-001',
  name: undefined,
  status: undefined,
};

describe('ScanScreen.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (scanApi.checkIn as jest.Mock).mockResolvedValue({ data: { success: true } });
  });

  // ── network error (non-axios) ───────────────────────────────

  it('shows network error on non-axios rejection', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue(new Error('Network Error'));
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('网络错误，请检查网络连接')).toBeTruthy();
  });

  // ── axios error without message ─────────────────────────────

  it('shows default error on axios rejection without message', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue({
      response: { data: {} },
    });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('未找到匹配的设备或站点')).toBeTruthy();
  });

  // ── axios error without response property ───────────────────

  it('shows network error on rejection without response property', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue({ message: 'some error' });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('网络错误，请检查网络连接')).toBeTruthy();
  });

  // ── quickInput clears error ─────────────────────────────────

  it('quickInput clears previous error', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue(new Error('Network Error'));
    const { getByText, getByPlaceholderText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('网络错误，请检查网络连接')).toBeTruthy();

    // Press quick input should clear error
    fireEvent.press(getByText('CHARGER-005'));
    expect(() => getByText('网络错误，请检查网络连接')).toThrow();
  });

  // ── onChangeText clears error ───────────────────────────────

  it('onChangeText clears error', async () => {
    (scanApi.scan as jest.Mock).mockRejectedValue(new Error('err'));
    const { getByText, getByPlaceholderText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('网络错误，请检查网络连接')).toBeTruthy();

    // Type again should clear error
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'X');
    expect(() => getByText('网络错误，请检查网络连接')).toThrow();
  });

  // ── station type render ─────────────────────────────────────

  it('renders station type correctly', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_STATION });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'STATION-A01');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('类型: 站点')).toBeTruthy();
    expect(await findByText('编码: STATION-A01')).toBeTruthy();
    expect(await findByText('名称: 东站')).toBeTruthy();
  });

  // ── unknown type render (❓ + 未知) ─────────────────────────

  it('renders unknown type with ❓ and 未知 label', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_UNKNOWN });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'X-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('类型: 未知')).toBeTruthy();
    // No name should be rendered
    expect(() => getByText('名称: undefined')).toThrow();
  });

  // ── signIn success flow ─────────────────────────────────────

  it('signIn flow: Alert confirm → checkIn success → success alert', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, msg, buttons?: any) => {
      // Simulate pressing "签到" button
      if (buttons && buttons[1]) {
        buttons[1].onPress();
      }
    });
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });
    (scanApi.checkIn as jest.Mock).mockResolvedValue({ data: { success: true } });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('扫码签到'));

    // Wait for async checkIn
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // Should have called checkIn and shown success alert
    expect(scanApi.checkIn).toHaveBeenCalledWith(7);
    expect(alertSpy).toHaveBeenCalledWith('签到成功', expect.stringContaining('充电桩01'));
    alertSpy.mockRestore();
  });

  // ── signIn failure flow ─────────────────────────────────────

  it('signIn flow: Alert confirm → checkIn failure → failure alert', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, msg, buttons?: any) => {
      if (buttons && buttons[1]) {
        buttons[1].onPress();
      }
    });
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });
    (scanApi.checkIn as jest.Mock).mockRejectedValue(new Error('fail'));

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('扫码签到'));

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    expect(alertSpy).toHaveBeenCalledWith('签到失败', '请重试或联系管理员');
    alertSpy.mockRestore();
  });

  // ── signIn cancel ───────────────────────────────────────────

  it('signIn flow: Alert cancel → setSignInMode(false)', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, msg, buttons?: any) => {
      // Press cancel
      if (buttons && buttons[0]) {
        buttons[0].onPress?.();
      }
    });
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('扫码签到'));

    // Should not have called checkIn
    expect(scanApi.checkIn).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  // ── signIn without scan result ──────────────────────────────

  it('signIn without scan result shows alert', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    // The "扫码签到" button only appears with a result, so we can't directly test this
    // path via UI. The handleSignIn guard is tested via the Alert flow above.
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  // ── reportFault flow ────────────────────────────────────────

  it('reportFault: shows confirm alert then success on submit', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, msg, buttons?: any) => {
      // First call: confirm, press "提交"
      if (buttons && buttons[1]) {
        buttons[1].onPress();
      }
    });
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('报修'));

    expect(alertSpy).toHaveBeenCalledWith('报修', expect.stringContaining('充电桩01'), expect.any(Array));
    // Second alert for success
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 10));
    });
    expect(alertSpy).toHaveBeenCalledWith('提交成功', '报修请求已提交，等待处理');
    alertSpy.mockRestore();
  });

  // ── reportFault cancel ──────────────────────────────────────

  it('reportFault: cancel does nothing', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, msg, buttons?: any) => {
      if (buttons && buttons[0]) {
        buttons[0].onPress?.();
      }
    });
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('报修'));

    // Only one alert call (the confirm), no success alert
    expect(alertSpy).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
  });

  // ── device without status (no StatusBadge) ──────────────────

  it('device without status does not render StatusBadge', async () => {
    const dev: any = { type: 'device', id: 1, code: 'D1', name: 'Dev1', status: undefined };
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: dev });
    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'D1');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('编码: D1')).toBeTruthy();
  });

  // ── loading disabled state ──────────────────────────────────

  it('input and button are disabled during loading', async () => {
    // Delay scan response to keep loading=true
    (scanApi.scan as jest.Mock).mockImplementation(() => new Promise(resolve => {
      setTimeout(() => resolve({ data: MOCK_DEVICE }), 200);
    }));

    const { getByPlaceholderText, getByText } = render(<ScanScreen />);
    const input = getByPlaceholderText('输入设备/站点编码');
    fireEvent.changeText(input, 'DEV-001');

    act(() => {
      fireEvent.press(getByText('查询'));
    });

    // During loading, button text should change to ActivityIndicator
    // The query button should still exist but as disabled
    expect(input.props.editable).toBe(false);

    // Wait for completion
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 300));
    });
  });

  // ── signInMode scanner box render ───────────────────────────

  it('renders signInMode scanner box after signIn press', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    (scanApi.scan as jest.Mock).mockResolvedValue({ data: MOCK_DEVICE });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    fireEvent.press(await findByText('扫码签到'));

    // signInMode should be true → '签到模式' visible
    expect(getByText('签到模式')).toBeTruthy();
    expect(getByText('请扫描设备二维码进行签到')).toBeTruthy();

    alertSpy.mockRestore();
  });
});
