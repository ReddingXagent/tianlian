/**
 * 天链V3 - 登录页测试 (更新: 2026-07-15 支持新角色选择流程)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import LoginPage from '../../src/pages/Login';
import { authAPI } from '../../src/api';

// Mock authAPI
vi.mock('../../src/api', () => ({
  authAPI: {
    login: vi.fn(),
    smsSend: vi.fn(),
    smsVerify: vi.fn(),
    smsLogin: vi.fn(),
    passwordReset: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...(actual as any),
    useNavigate: () => mockNavigate,
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

function renderLogin() {
  return render(
    <BrowserRouter>
      <LoginPage />
    </BrowserRouter>
  );
}

/** Select a role card by clicking its "进入" button (index 0=运营, 1=运维, 2=车队, 3=平台) */
function selectRole(index: number) {
  const enterBtns = screen.getAllByText('进入');
  fireEvent.click(enterBtns[index]);
}

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  describe('角色选择页面', () => {
    it('应正确渲染标题和副标题', () => {
      renderLogin();
      expect(screen.getByText('天链光储充运维系统')).toBeTruthy();
      expect(screen.getByText('请选择您的登录入口')).toBeTruthy();
    });

    it('应显示所有四个角色卡片', () => {
      renderLogin();
      expect(screen.getByText('运营管理')).toBeTruthy();
      expect(screen.getByText('运维管理')).toBeTruthy();
      expect(screen.getByText('车队管理')).toBeTruthy();
      expect(screen.getByText('平台管理')).toBeTruthy();
    });

    it('应显示进入按钮', () => {
      renderLogin();
      expect(screen.getAllByText('进入').length).toBe(4);
    });

    it('点击运维管理角色应进入登录表单', () => {
      renderLogin();
      selectRole(1); // 运维管理
      // 进入登录表单后，应显示欢迎文字与密码登录输入框
      // (任务卡 78c7404b: 验证码登录已停用, 仅保留密码登录入口)
      expect(screen.getByText('欢迎回来，运维管理')).toBeTruthy();
      expect(screen.getByPlaceholderText('请输入用户名')).toBeTruthy();
      expect(screen.getByPlaceholderText('请输入密码')).toBeTruthy();
    });
  });

  describe('登录表单 - 密码登录', () => {
    it('默认应为密码登录模式', () => {
      renderLogin();
      selectRole(1);
      expect(screen.getByPlaceholderText('请输入用户名')).toBeTruthy();
      expect(screen.getByPlaceholderText('请输入密码')).toBeTruthy();
    });

    it('空字段时应显示错误提示', async () => {
      renderLogin();
      selectRole(1);
      fireEvent.click(screen.getByText('登 录'));
      await waitFor(() => {
        expect(screen.getByText('请输入用户名和密码')).toBeTruthy();
      });
    });

    it('成功登录应跳转到默认路由', async () => {
      (authAPI.login as any).mockResolvedValue({
        data: {
          token: 'test-token',
          user: { username: 'admin', role: 'ADMIN' },
        },
      });
      renderLogin();
      selectRole(1);
      fireEvent.change(screen.getByPlaceholderText('请输入用户名'), {
        target: { value: 'admin' },
      });
      fireEvent.change(screen.getByPlaceholderText('请输入密码'), {
        target: { value: 'admin123' },
      });
      fireEvent.click(screen.getByText('登 录'));
      await waitFor(() => {
        expect(localStorage.getItem('admin_token')).toBe('test-token');
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
      });
    });
  });

  describe('忘记密码弹窗', () => {
    it('点击忘记密码应弹出重置密码弹窗', () => {
      renderLogin();
      selectRole(1);
      fireEvent.click(screen.getByText('忘记密码？'));
      expect(screen.getByText('重置密码')).toBeTruthy();
    });

    it('发送重置验证码应调用API', async () => {
      (authAPI.smsSend as any).mockResolvedValue({ data: {} });
      renderLogin();
      selectRole(1);
      fireEvent.click(screen.getByText('忘记密码？'));
      const phoneInputs = screen.getAllByPlaceholderText('请输入手机号');
      fireEvent.change(phoneInputs[phoneInputs.length - 1], { target: { value: '13800138000' } });
      const getCodeBtns = screen.getAllByText('获取验证码');
      fireEvent.click(getCodeBtns[getCodeBtns.length - 1]);
      await waitFor(() => {
        expect(authAPI.smsSend).toHaveBeenCalledWith('13800138000', 'reset');
      });
    });
  });

  describe('验证码发送', () => {
    it('忘记密码获取验证码按钮应触发API调用', async () => {
      // (任务卡 78c7404b: 验证码登录已停用; 获取验证码现仅服务于忘记密码重置流程)
      (authAPI.smsSend as any).mockResolvedValue({ data: {} });
      renderLogin();
      selectRole(1);
      fireEvent.click(screen.getByText('忘记密码？'));
      const phoneInputs = screen.getAllByPlaceholderText('请输入手机号');
      fireEvent.change(phoneInputs[phoneInputs.length - 1], {
        target: { value: '13800138000' },
      });
      const getCodeBtns = screen.getAllByText('获取验证码');
      fireEvent.click(getCodeBtns[getCodeBtns.length - 1]);
      await waitFor(() => {
        expect(authAPI.smsSend).toHaveBeenCalledWith('13800138000', 'reset');
      });
    });
  });
});