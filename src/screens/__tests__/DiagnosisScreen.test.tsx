import { render, fireEvent, act } from '@testing-library/react-native';
import DiagnosisScreen from '../DiagnosisScreen';
import { diagnosisApi } from '../../services/api';

jest.mock('../../services/api', () => ({
  diagnosisApi: { getDiagnosis: jest.fn() },
}));

const MOCK_DIAG = {
  faultCode: 'E001',
  description: '过压故障',
  severity: 'high',
  possibleCauses: ['原因一', '原因二'],
  solutions: ['方案一'],
  deviceType: 'charger',
  relatedArticles: [
    { id: 1, title: '相关文章', authorName: '张三', viewCount: 5 },
  ],
};

describe('DiagnosisScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders search box, examples and empty state', () => {
    const { getByText, getByPlaceholderText } = render(<DiagnosisScreen />);
    expect(getByPlaceholderText('输入故障码（如 E001）')).toBeTruthy();
    expect(getByText('常见故障码:')).toBeTruthy();
    expect(getByText('E001-过压')).toBeTruthy();
    expect(getByText('故障码诊断')).toBeTruthy();
  });

  it('shows error when code is empty', () => {
    const { getByText } = render(<DiagnosisScreen />);
    fireEvent.press(getByText('查询'));
    expect(getByText('请输入故障码')).toBeTruthy();
  });

  it('fills input via a quick example button', () => {
    const { getByText, getByPlaceholderText } = render(<DiagnosisScreen />);
    fireEvent.press(getByText('E002-过流'));
    expect(getByPlaceholderText('输入故障码（如 E001）').props.value).toBe('E002');
  });

  it('shows diagnosis result on success', async () => {
    (diagnosisApi.getDiagnosis as jest.Mock).mockResolvedValue({ data: MOCK_DIAG });
    const { getByPlaceholderText, getByText, findByText } = render(
      <DiagnosisScreen />
    );
    fireEvent.changeText(getByPlaceholderText('输入故障码（如 E001）'), 'E001');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(await findByText('E001')).toBeTruthy();
    expect(await findByText('过压故障')).toBeTruthy();
    expect(await findByText('📋 可能原因')).toBeTruthy();
    expect(await findByText('原因一')).toBeTruthy();
    expect(await findByText('💡 解决方案')).toBeTruthy();
    expect(await findByText('方案一')).toBeTruthy();
    expect(await findByText('相关文章')).toBeTruthy();
  });

  it('shows error for an unknown fault code', async () => {
    (diagnosisApi.getDiagnosis as jest.Mock).mockRejectedValue(new Error('nf'));
    const { getByPlaceholderText, getByText, findByText } = render(
      <DiagnosisScreen />
    );
    fireEvent.changeText(getByPlaceholderText('输入故障码（如 E001）'), 'EXXX');
    await act(async () => {
      fireEvent.press(getByText('查询'));
    });
    expect(
      await findByText('未找到该故障码，请确认故障码是否正确')
    ).toBeTruthy();
  });
});
