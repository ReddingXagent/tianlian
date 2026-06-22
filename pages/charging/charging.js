// pages/charging/charging.js - 充电中
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');

Page({
  data: {
    sessionId: '',
    chargerId: '',
    orderId: '',

    // 实时数据
    power: '0.00',       // 实时功率 (kW)
    energy: '0.00',      // 已充电量 (kWh)
    cost: '0.00',        // 当前费用 (元)
    duration: 0,         // 已充时长 (分钟)
    soc: 0,              // 充电进度 (%)
    voltage: '0',        // 电压 (V)
    current: '0',        // 电流 (A)
    temp: '0',           // 温度 (°C)
    price: '0.00',       // 单价 (元/度)

    // 状态
    statusText: '充电中',
    statusClass: 'charging',
    startTime: '',

    // 轮询
    pollTimer: null
  },

  onLoad(options) {
    const { sessionId, chargerId } = options;
    this.setData({
      sessionId,
      chargerId: chargerId || '',
      startTime: util.formatTime(new Date(), 'HH:mm:ss')
    });

    // 开始轮询
    this.startPolling();
  },

  onUnload() {
    this.stopPolling();
  },

  onHide() {
    // 切后台时停止轮询
    this.stopPolling();
  },

  onShow() {
    // 切回前台时恢复轮询
    if (this.data.sessionId) {
      this.startPolling();
    }
  },

  // 开始轮询
  startPolling() {
    this.fetchStatus(); // 立即获取一次
    const timer = setInterval(() => {
      this.fetchStatus();
    }, config.CHARGING_POLL_INTERVAL);
    this.setData({ pollTimer: timer });
  },

  // 停止轮询
  stopPolling() {
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer);
      this.setData({ pollTimer: null });
    }
  },

  // 获取充电状态
  async fetchStatus() {
    try {
      const res = await api.getChargingStatus(this.data.sessionId);
      const data = res.data || {};

      this.setData({
        power: (data.power || 0).toFixed(2),
        energy: (data.energy || 0).toFixed(2),
        cost: (data.cost || 0).toFixed(2),
        duration: data.duration || 0,
        soc: data.soc || 0,
        voltage: String(data.voltage || 0),
        current: String(data.current || 0),
        temp: String(data.temperature || 0),
        price: (data.price || 0).toFixed(2),
        orderId: data.orderId || '',
        statusText: data.status === 'charging' ? '充电中' : data.status || '充电中'
      });

      // 充电完成自动跳转
      if (data.status === 'finished') {
        this.stopPolling();
        wx.showToast({ title: '充电完成', icon: 'success' });
        setTimeout(() => {
          wx.redirectTo({
            url: `/pages/order-detail/order-detail?orderId=${data.orderId}`
          });
        }, 1500);
      }
    } catch (err) {
      console.error('获取充电状态失败:', err);
      // 连续失败3次停止轮询
      if (!this._failCount) this._failCount = 0;
      this._failCount++;
      if (this._failCount >= 3) {
        this.stopPolling();
        wx.showToast({ title: '连接异常，请刷新', icon: 'none' });
      }
    }
  },

  // 停止充电
  onStopCharging() {
    wx.showModal({
      title: '确认停止',
      content: '确定要停止充电吗？',
      confirmColor: '#FA5151',
      success: async (modalRes) => {
        if (modalRes.confirm) {
          try {
            await api.stopCharging(this.data.sessionId);
            this.stopPolling();
            wx.showToast({ title: '已停止充电', icon: 'success' });
            setTimeout(() => {
              wx.redirectTo({
                url: `/pages/order-detail/order-detail?orderId=${this.data.orderId}`
              });
            }, 1000);
          } catch (err) {
            console.error('停止充电失败:', err);
          }
        }
      }
    });
  }
});
