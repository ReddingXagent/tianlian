// pages/charging/charging.js - 充电中
// 性能优化：智能轮询（自适应间隔 + 失败退避）+ 批量 setData
const api = require('../../services/api');
const util = require('../../utils/util');
const config = require('../../config/index');
const { createPolling } = require('../../utils/polling');
const { diffSetData } = require('../../utils/perf');

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

    // 轮询状态
    pollingActive: false
  },

  onLoad(options) {
    const { sessionId, chargerId } = options;
    this.setData({
      sessionId,
      chargerId: chargerId || '',
      startTime: util.formatTime(new Date(), 'HH:mm:ss')
    });

    this._polling = null;
    this._lastStatusData = null; // 用于 diff 比较的上次数据
  },

  onShow() {
    // 切回前台时恢复轮询
    if (this.data.sessionId && !this.data.pollingActive) {
      this.startPolling();
    }
  },

  onHide() {
    // 切后台时停止轮询
    this.stopPolling();
  },

  onUnload() {
    this.stopPolling();
  },

  // 开始智能轮询
  startPolling() {
    if (this._polling) {
      this._polling.stop();
    }

    this._polling = createPolling(
      () => this.fetchStatus(),
      {
        interval: config.CHARGING_POLL_INTERVAL,
        maxRetries: 3,
        backoffFactor: 1.5,
        maxInterval: 15000,
        shouldStop: () => this.data.statusText === '充电完成',
        onMaxRetries: () => {
          wx.showToast({ title: '连接异常，请刷新', icon: 'none' });
          this.setData({ pollingActive: false });
        }
      }
    );

    this.setData({ pollingActive: true });
    this._polling.start();
  },

  // 停止轮询
  stopPolling() {
    if (this._polling) {
      this._polling.stop();
      this._polling = null;
    }
    this.setData({ pollingActive: false });
  },

  // 获取充电状态（批量 setData + diff，减少渲染次数）
  async fetchStatus() {
    try {
      const res = await api.getChargingStatus(this.data.sessionId);
      const data = res.data || {};

      // 构建新数据对象
      const newData = {
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
      };

      // diff 更新：只发送变化的字段
      diffSetData(this, newData, this._lastStatusData);
      this._lastStatusData = newData;

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
      throw err; // 交给 polling 处理退避
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
