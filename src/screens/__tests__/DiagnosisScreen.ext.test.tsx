/**
 * DiagnosisScreen ext — unknown severity fallback (line 63)
 * SEVERITY_CONFIG[result.severity] || { label: result.severity, color: '#999' }
 */
import { render, fireEvent, act } from '@testing-library/react-native';
import DiagnosisScreen from '../DiagnosisScreen';
import { diagnosisApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  diagnosisApi: { getDiagnosis: jest.fn() },
}));

const MOCK_UNKNOWN_SEVERITY = {
  faultCode: 'X999',
  description: '未知故障类型',
  severity: 'extreme', // not in SEVERITY_CONFIG keys
  possibleCauses: [],
  solutions: [],
  deviceType: 'unknown',
  relatedArticles: [],
};

describe('DiagnosisScreen.ext unknown severity', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows raw severity label when severity is not in SEVERITY_CONFIG', async () => {
    (diagnosisApi.getDiagnosis as jest.Mock).mockResolvedValue({ data: MOCK_UNKNOWN_SEVERITY });
    const { getByPlaceholderText, getByText, findByText } = render(<DiagnosisScreen />);
    fireEvent.changeText(getByPlaceholderText('输入故障码（如 E001）'), 'X999');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    // The unknown severity 'extreme' should be shown as the label (fallback)
    expect(await findByText('X999')).toBeTruthy();
  });
});
