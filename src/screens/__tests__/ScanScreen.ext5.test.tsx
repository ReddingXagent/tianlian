/**
 * ScanScreen.ext5 — coverage 100% closure
 * - L77 col59-74: sign-in SUCCESS alert `name || code` fallback (name:'')
 *   (ext3 covered the confirm dialog fallback L70; the SUCCESS alert at L77
 *    was only ever exercised with name set → b6 arm1 never hit)
 * - L61-64 / L91-94 guards: UI-unreachable defensive code (buttons render
 *   only inside lastResult!=null block — probe-verified F1215). Per F1214
 *   istanbul methodology: only true reachable gaps get tests; defensive
 *   guards documented here, not artificially forced.
 */
import React from 'react';
import { render, fireEvent, act } from '@testing-library/react-native';
import { Alert, type AlertButton } from 'react-native';
import ScanScreen from '../ScanScreen';
import { scanApi } from '../../services/api';

jest.mock('../../services/api', () => ({
  scanApi: { scan: jest.fn(), checkIn: jest.fn() },
}));

describe('ScanScreen.ext5', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(
      (title: string, message?: string, buttons?: AlertButton[]) => {
        // Auto-confirm: press the action button (index 1) when present
        if (buttons && buttons[1] && buttons[1].onPress) {
          buttons[1].onPress();
        }
      }
    );
  });

  afterEach(() => {
    alertSpy.mockRestore();
  });

  // L77: sign-in SUCCESS alert falls back to code when name is empty.
  // Fail-fast anchors: query → result rendered → confirm → checkIn called →
  // success alert contains the code fallback text.
  it('sign-in success alert uses code fallback when name is empty (L77)', async () => {
    (scanApi.scan as jest.Mock).mockResolvedValue({
      data: { type: 'device', id: 9, code: 'DEV-NO-NAME', name: '', status: 'online' },
    });
    (scanApi.checkIn as jest.Mock).mockResolvedValue({ data: { success: true } });

    const { getByPlaceholderText, getByText, findByText } = render(<ScanScreen />);
    fireEvent.changeText(getByPlaceholderText('输入设备/站点编码'), 'DEV-NO-NAME');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });

    // Fail-fast: result with sign-in button must be rendered
    expect(await findByText('扫码签到')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('扫码签到'));
    });
    // Let the async checkIn + alert chain settle
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    // Fail-fast anchors: checkIn really called, success alert with code fallback
    expect(scanApi.checkIn).toHaveBeenCalledTimes(1);
    expect(scanApi.checkIn).toHaveBeenCalledWith(9);
    expect(alertSpy).toHaveBeenCalledWith('签到成功', '已在 DEV-NO-NAME 签到');
  });
});
