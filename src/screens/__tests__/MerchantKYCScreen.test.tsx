/**
 * MerchantKYCScreen.test.tsx — 商户进件屏幕全流程测试 (卡 a8ca56aa)
 * 走默认 mock 通道 (内存实现), 覆盖: 表单校验/提交/四态状态视图/驳回重提/错误面
 */
import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import MerchantKYCScreen from '../MerchantKYCScreen';
import { __mockStore } from '../../services/merchant-mock';
import { merchantKyc } from '../../services/merchant-source';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const FIELD_VALUES: Record<string, string> = {
  'kyc-field-company': '测试能源有限公司',
  'kyc-field-uscc': '91440300MA5ABC1234',
  'kyc-field-contact': '张三',
  'kyc-field-phone': '13800138000',
  'kyc-field-bank-name': '工商银行深圳分行',
  'kyc-field-bank-account': '1234567890',
};

const PHOTO_IDS = ['kyc-photo-license', 'kyc-photo-idfront', 'kyc-photo-idback', 'kyc-photo-bankcard'];

/** 填全 6 字段 + 选满 4 证照 */
const fillAndPick = (getByTestId: (id: string) => { props: { testID?: string } } & Parameters<typeof fireEvent.press>[0]) => {
  Object.entries(FIELD_VALUES).forEach(([id, value]) => {
    fireEvent.changeText(getByTestId(id), value);
  });
  PHOTO_IDS.forEach((id) => {
    fireEvent.press(getByTestId(id));
  });
};

beforeEach(() => {
  jest.clearAllMocks();
  __mockStore.reset();
});

describe('MerchantKYCScreen 表单视图', () => {
  it('渲染 6 字段 + 4 证照槽 + 提交按钮 + 模拟通道标识', () => {
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    Object.keys(FIELD_VALUES).forEach((id) => expect(getByTestId(id)).toBeTruthy());
    PHOTO_IDS.forEach((id) => expect(getByTestId(id)).toBeTruthy());
    expect(getByTestId('kyc-submit-btn')).toBeTruthy();
    expect(getByText('数据通道：模拟通道（契约未定）')).toBeTruthy();
  });

  it('空表单提交 → 逐项校验错误, 不进入状态视图', () => {
    const { getByTestId, queryByTestId, getByText } = render(<MerchantKYCScreen />);
    fireEvent.press(getByTestId('kyc-submit-btn'));
    expect(getByText('请输入企业名称')).toBeTruthy();
    expect(getByText('请输入11位手机号')).toBeTruthy();
    expect(getByText('请补齐全部证件照')).toBeTruthy();
    expect(queryByTestId('kyc-status-card')).toBeNull();
  });

  it('部分非法字段 → 定向错误提示', () => {
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    fireEvent.changeText(getByTestId('kyc-field-company'), '测试能源有限公司');
    fireEvent.changeText(getByTestId('kyc-field-uscc'), '123');
    fireEvent.changeText(getByTestId('kyc-field-contact'), '张三');
    fireEvent.changeText(getByTestId('kyc-field-phone'), '12345');
    fireEvent.changeText(getByTestId('kyc-field-bank-name'), '工商银行');
    fireEvent.changeText(getByTestId('kyc-field-bank-account'), 'abc');
    PHOTO_IDS.forEach((id) => fireEvent.press(getByTestId(id)));
    fireEvent.press(getByTestId('kyc-submit-btn'));
    expect(getByText('统一社会信用代码须为18位数字或大写字母')).toBeTruthy();
    expect(getByText('请输入11位手机号')).toBeTruthy();
    expect(getByText('结算账号须为9-30位数字')).toBeTruthy();
  });

  it('选照后槽位状态翻转', () => {
    const { getByTestId, getAllByText } = render(<MerchantKYCScreen />);
    expect(getAllByText('点击上传')).toHaveLength(4);
    fireEvent.press(getByTestId('kyc-photo-license'));
    expect(getAllByText('已选择')).toHaveLength(1);
    expect(getAllByText('点击上传')).toHaveLength(3);
  });

  it('提交失败 (Error) → 错误文案, 留在表单视图', async () => {
    const spy = jest.spyOn(merchantKyc, 'submitApplication').mockRejectedValueOnce(new Error('网络异常'));
    const { getByTestId, getByText, queryByTestId } = render(<MerchantKYCScreen />);
    fillAndPick(getByTestId);
    fireEvent.press(getByTestId('kyc-submit-btn'));
    await waitFor(() => {
      expect(getByTestId('kyc-error-text')).toBeTruthy();
    });
    expect(getByText('网络异常')).toBeTruthy();
    expect(queryByTestId('kyc-status-card')).toBeNull();
    spy.mockRestore();
  });

  it('提交失败 (非 Error) → 兜底文案', async () => {
    const spy = jest.spyOn(merchantKyc, 'submitApplication').mockRejectedValueOnce('boom');
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    fillAndPick(getByTestId);
    fireEvent.press(getByTestId('kyc-submit-btn'));
    await waitFor(() => {
      expect(getByText('提交失败，请稍后重试')).toBeTruthy();
    });
    spy.mockRestore();
  });
});

describe('MerchantKYCScreen 状态视图', () => {
  const submitValid = async (getByTestId: (id: string) => Parameters<typeof fireEvent.press>[0]) => {
    fillAndPick(getByTestId as Parameters<typeof fillAndPick>[0]);
    fireEvent.press(getByTestId('kyc-submit-btn'));
    await waitFor(() => {
      expect(getByTestId('kyc-status-card')).toBeTruthy();
    });
  };

  it('提交成功 → 待审核 + 申请编号 1001 + 表单视图消失', async () => {
    const { getByTestId, getByText, queryByTestId } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    expect(getByText('待审核')).toBeTruthy();
    expect(getByText('申请编号：1001')).toBeTruthy();
    expect(queryByTestId('kyc-field-company')).toBeNull();
    expect(__mockStore.current?.status).toBe('pending');
  });

  it('audit 态: 刷新后显示审核中', async () => {
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    __mockStore.setStatus('audit');
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => {
      expect(getByText('审核中')).toBeTruthy();
    });
  });

  it('approved 态: 通过提示 + 无重新提交按钮', async () => {
    const { getByTestId, getByText, queryByTestId } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    __mockStore.setStatus('approved');
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => {
      expect(getByText('已通过')).toBeTruthy();
    });
    expect(getByTestId('kyc-approved-hint')).toBeTruthy();
    expect(queryByTestId('kyc-resubmit-btn')).toBeNull();
  });

  it('rejected 态: 驳回原因 + 重新提交回表单且预填', async () => {
    const { getByTestId, getByText, queryByTestId, getByDisplayValue } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    __mockStore.setStatus('rejected', '执照模糊');
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => {
      expect(getByText('已驳回')).toBeTruthy();
    });
    expect(getByTestId('kyc-reject-reason')).toBeTruthy();
    expect(getByText('驳回原因：执照模糊')).toBeTruthy();
    fireEvent.press(getByTestId('kyc-resubmit-btn'));
    expect(queryByTestId('kyc-status-card')).toBeNull();
    expect(getByDisplayValue('测试能源有限公司')).toBeTruthy();
    expect(getByDisplayValue('91440300MA5ABC1234')).toBeTruthy();
  });

  it('刷新失败 (Error) → 透出错误信息', async () => {
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    const spy = jest.spyOn(merchantKyc, 'getApplication').mockRejectedValueOnce(new Error('云端超时'));
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => {
      expect(getByText('云端超时')).toBeTruthy();
    });
    spy.mockRestore();
  });

  it('刷新失败 (非 Error) → 兜底文案', async () => {
    const { getByTestId, getByText } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    const spy = jest.spyOn(merchantKyc, 'getApplication').mockRejectedValueOnce('x');
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => {
      expect(getByText('刷新失败，请稍后重试')).toBeTruthy();
    });
    spy.mockRestore();
  });

  it('刷新无数据 (store 清空) → 保留旧状态, 不报错', async () => {
    const { getByTestId, getByText, queryByTestId } = render(<MerchantKYCScreen />);
    await submitValid(getByTestId);
    __mockStore.reset();
    const spy = jest.spyOn(merchantKyc, 'getApplication');
    fireEvent.press(getByTestId('kyc-refresh-btn'));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 250)); // 等 mock 延迟返回 null 走完 if(latest) 假臂
    expect(getByText('待审核')).toBeTruthy();
    expect(queryByTestId('kyc-error-text')).toBeNull();
    spy.mockRestore();
  });
});
