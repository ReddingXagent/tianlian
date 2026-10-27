// __tests__/app.test.js
// F770: App全局错误处理生命周期测试
const mockShowToast = jest.fn();
const mockSwitchTab = jest.fn();
const mockNavigateTo = jest.fn();
const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();
const mockRemoveStorageSync = jest.fn();
const mockShowLoading = jest.fn();
const mockHideLoading = jest.fn();
const mockWxRequest = jest.fn();
const mockWxLogin = jest.fn();

global.wx = {
  request: mockWxRequest,
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
  removeStorageSync: mockRemoveStorageSync,
  showLoading: mockShowLoading,
  hideLoading: mockHideLoading,
  showToast: mockShowToast,
  switchTab: mockSwitchTab,
  navigateTo: mockNavigateTo,
  login: mockWxLogin
};

// 捕获App()注册的配置对象
let appConfig = null;
global.App = (config) => { appConfig = config; };

// 抑制console.error输出
const origConsoleError = console.error;
console.error = jest.fn();

require('../app');

describe('F770: App全局错误处理', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('onError', () => {
    it('JS异常触发toast提示', () => {
      const err = new Error('test crash');
      appConfig.onError(err);
      expect(mockShowToast).toHaveBeenCalledWith({
        title: '小程序内部错误',
        icon: 'none',
        duration: 2000
      });
    });

    it('字符串错误也能处理', () => {
      appConfig.onError('string error');
      expect(mockShowToast).toHaveBeenCalledTimes(1);
    });
  });

  describe('onPageNotFound', () => {
    it('404页面重定向到首页', () => {
      appConfig.onPageNotFound({ path: '/pages/nonexistent/index' });
      expect(mockSwitchTab).toHaveBeenCalledWith({
        url: '/pages/index/index'
      });
    });
  });

  describe('onUnhandledRejection', () => {
    it('未捕获Promise rejection不崩溃', () => {
      const reason = new Error('unhandled');
      appConfig.onUnhandledRejection({ reason });
      // 不应触发toast（静默记录即可）
      expect(mockShowToast).not.toHaveBeenCalled();
    });
  });
});

// 恢复console.error
console.error = origConsoleError;
