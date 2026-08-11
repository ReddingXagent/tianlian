// app.js - 天链充电小程序入口
const api = require('./services/api');
const branding = require('./utils/branding');
const config = require('./config/index');

App({
  globalData: {
    token: null,
    userInfo: null,
    // 当前充电会话
    chargingSession: null,
    // 静默重试标记
    _reloginPending: null,
    // 当前租户ID（由场景参数或登录态决定）
    tenantId: null,
    // 租户品牌缓存
    tenantBranding: null
  },

  onLaunch() {
    // 检查登录状态
    // 注: 原wx.getSystemInfoSync()已废弃(2.20.1+)且systemInfo无消费方，已移除(F40)
    this.checkLogin();
    // 加载租户品牌（先读缓存即时生效，再异步拉取最新）
    this.initTenantBranding();
  },

  // F770: 全局错误捕获 — 防止JS异常导致白屏
  onError(err) {
    console.error('[App.onError]', err);
    wx.showToast({ title: '小程序内部错误', icon: 'none', duration: 2000 });
  },

  // F770: 页面不存在兜底
  onPageNotFound(res) {
    console.error('[App.onPageNotFound]', res.path);
    wx.switchTab({ url: '/pages/index/index' });
  },

  // F770: 未处理的Promise rejection
  onUnhandledRejection(res) {
    console.error('[App.onUnhandledRejection]', res.reason);
  },

  onShow(options) {
    // 从扫码进入时处理场景
    if (options.query && options.query.scene) {
      this.handleScene(options.query.scene);
    }
  },

  // 检查登录状态
  checkLogin() {
    const token = wx.getStorageSync('token');
    if (token) {
      this.globalData.token = token;
      // 验证token有效性
      api.getUserInfo()
        .then(res => {
          this.globalData.userInfo = res.data;
        })
        .catch(() => {
          // token失效，清除
          this.clearLogin();
        });
    }
  },

  // 执行登录
  login() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: (loginRes) => {
          if (loginRes.code) {
            api.login(loginRes.code)
              .then(res => {
                const { token, userInfo } = res.data;
                wx.setStorageSync('token', token);
                this.globalData.token = token;
                this.globalData.userInfo = userInfo;
                resolve(userInfo);
              })
              .catch(reject);
          } else {
            reject(new Error('登录失败'));
          }
        },
        fail: reject
      });
    });
  },

  // 清除登录状态
  clearLogin() {
    wx.removeStorageSync('token');
    this.globalData.token = null;
    this.globalData.userInfo = null;
  },

  // 静默重登（token过期时自动重试）
  silentRelogin() {
    if (this.globalData._reloginPending) {
      return this.globalData._reloginPending;
    }
    this.globalData._reloginPending = this.login()
      .finally(() => {
        this.globalData._reloginPending = null;
      });
    return this.globalData._reloginPending;
  },

  // 处理扫码场景
  handleScene(scene) {
    // scene 为设备二维码内容，如 chargerId
    wx.navigateTo({
      url: `/pages/charging/charging?chargerId=${scene}`
    });
  },

  // 获取全局token
  getToken() {
    return this.globalData.token || wx.getStorageSync('token');
  },

  // 初始化租户品牌：先读缓存即时应用，再异步拉最新
  initTenantBranding(tenantId) {
    const tid = tenantId || this.globalData.tenantId || 'default';
    // 1. 读缓存，即时生效（不阻塞启动）
    const cached = branding.getCachedTenantBranding();
    if (cached) {
      this.globalData.tenantBranding = cached;
      branding.applyBrandingToApp(cached);
    }
    // 2. 异步拉取最新（静默，失败用缓存/默认）
    api.getTenantBranding(tid)
      .then((res) => {
        const normalized = branding.normalizeBranding(res.data);
        this.globalData.tenantBranding = normalized;
        branding.cacheTenantBranding(normalized, config.CACHE_TTL.TENANT_BRANDING);
        branding.applyBrandingToApp(normalized);
      })
      .catch(() => {
        // 静默失败，使用缓存或默认品牌
      });
  },

  // F770: 应用全局错误状态标记 (onError触发后页面可读取做降级UI)
  // 获取全局用户信息(F239: 与getToken同构的storage兜底本地访问器;
  // 冷启动onLaunch走api.getUserInfo()异步回填, 请求未回/失败时globalData为空,
  // 页面直读globalData.userInfo=空态, 兜底storage保证登录态本地可读)
  getUserInfo() {
    return this.globalData.userInfo || wx.getStorageSync('userInfo');
  }
});
