/**
 * useDiagnosis Hook 测试
 */
import { renderHook, act } from '@testing-library/react-native';

jest.mock('../../services/api', () => ({
  diagnosisApi: {
    getDiagnosis: jest.fn(),
  },
}));

import { useDiagnosis } from '../useDiagnosis';
import { diagnosisApi } from '../../services/api';

const mockGetDiagnosis = diagnosisApi.getDiagnosis as jest.MockedFunction<typeof diagnosisApi.getDiagnosis>;

const MOCK_RESULT = {
  code: 'E001',
  description: '电池过压',
  suggestion: '检查电池模块',
  severity: 'high',
};

describe('useDiagnosis', () => {
  beforeEach(() => jest.clearAllMocks());

  it('初始状态', () => {
    const { result } = renderHook(() => useDiagnosis());
    expect(result.current.codeInput).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('空输入 → 错误"请输入故障码"', async () => {
    const { result } = renderHook(() => useDiagnosis());
    await act(async () => { await result.current.handleSearch(); });
    expect(result.current.error).toBe('请输入故障码');
    expect(mockGetDiagnosis).not.toHaveBeenCalled();
  });

  it('仅空格 → 错误"请输入故障码"', async () => {
    const { result } = renderHook(() => useDiagnosis());
    act(() => result.current.setCodeInput('   '));
    await act(async () => { await result.current.handleSearch(); });
    expect(result.current.error).toBe('请输入故障码');
  });

  it('成功查询: result设置+codeInput清空', async () => {
    mockGetDiagnosis.mockResolvedValueOnce({ data: MOCK_RESULT });
    const { result } = renderHook(() => useDiagnosis());
    act(() => result.current.setCodeInput('E001'));
    await act(async () => { await result.current.handleSearch(); });
    expect(mockGetDiagnosis).toHaveBeenCalledWith('E001');
    expect(result.current.result).toEqual(MOCK_RESULT);
    expect(result.current.codeInput).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('查询失败: 显示错误, result为null', async () => {
    mockGetDiagnosis.mockRejectedValueOnce(new Error('404'));
    const { result } = renderHook(() => useDiagnosis());
    act(() => result.current.setCodeInput('E999'));
    await act(async () => { await result.current.handleSearch(); });
    expect(result.current.error).toBe('未找到该故障码，请确认故障码是否正确');
    expect(result.current.result).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('handleQuickInput 设置code并清除错误', async () => {
    const { result } = renderHook(() => useDiagnosis());
    await act(async () => { await result.current.handleSearch(); });
    expect(result.current.error).not.toBeNull();
    act(() => result.current.handleQuickInput('E002'));
    expect(result.current.codeInput).toBe('E002');
    expect(result.current.error).toBeNull();
  });

  it('clearError 清除错误', async () => {
    const { result } = renderHook(() => useDiagnosis());
    await act(async () => { await result.current.handleSearch(); });
    expect(result.current.error).not.toBeNull();
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });
});
