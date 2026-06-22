// pages/scan/scan.js - 扫码充电
const api = require('../../services/api');
const util = require('../../utils/util');

Page({
  data: {
    chargerId: '',
    history: []
  },

  onLoad() {
    this.loadHistory();
  },

  onShow() {
    this.loadHistory();
  },

  // 扫码
  onScanCode() {
    wx.scanCode({
      onlyFromCamera: true,
      scanType: ['qrCode', 'barCode'],
      success: (res) => {
        const chargerId = this.parseChargerId(res.result);
        if (chargerId) {
          this.startCharging(chargerId);
        } else {
          wx.showToast({
            title: '无效的充电桩二维码',
            icon: 'none'
          });
        }
      },
      fail: (err) => {
        if (err.errMsg !== 'scanCode:fail cancel') {
          wx.showToast({
            title: '扫码失败，请重试',
            icon: 'none'
          });
        }
      }
    });
  },

  // 解析充电桩ID
  parseChargerId(result) {
    // 支持多种格式：
    // 1. 纯ID: "CHARGER_001"
    // 2. URL: "https://xxx.com/charger/CHARGER_001"
    // 3. JSON: {"chargerId": "CHARGER_001"}

    if (!result) return null;

    // 尝试JSON解析
    try {
      const json = JSON.parse(result);
      if (json.chargerId) return json.chargerId;
      if (json.id) return json.id;
    } catch (e) {
      // 非JSON，继续
    }

    // URL解析
    const urlMatch = result.match(/charger[\/=]([A-Za-z0-9_-]+)/);
    if (urlMatch) return urlMatch[1];

    // 纯ID
    if (/^[A-Za-z0-9_-]+$/.test(result.trim())) {
      return result.trim();
    }

    return null;
  },

  // 输入变化
  onInputChange(e) {
    this.setData({ chargerId: e.detail.value });
  },

  // 手动输入启动
  onManualStart() {
    const { chargerId } = this.data;
    if (!chargerId.trim()) {
      wx.showToast({ title: '请输入充电桩编号', icon: 'none' });
      return;
    }
    this.startCharging(chargerId.trim());
  },

  // 启动充电
  async startCharging(chargerId) {
    try {
      const res = await api.startCharging(chargerId);
      // 保存到历史
      this.saveHistory(chargerId, res.data);

      // 跳转到充电页面
      wx.navigateTo({
        url: `/pages/charging/charging?sessionId=${res.data.sessionId}&chargerId=${chargerId}`
      });
    } catch (err) {
      console.error('启动充电失败:', err);
    }
  },

  // 历史记录点击
  onHistoryTap(e) {
    const { id } = e.currentTarget.dataset;
    this.startCharging(id);
  },

  // 加载历史记录
  loadHistory() {
    try {
      const history = wx.getStorageSync('scanHistory') || [];
      this.setData({ history });
    } catch (e) {
      // ignore
    }
  },

  // 保存历史记录
  saveHistory(chargerId, sessionData) {
    try {
      let history = wx.getStorageSync('scanHistory') || [];
      // 去重
      history = history.filter(h => h.id !== chargerId);
      // 添加到最前
      history.unshift({
        id: chargerId,
        name: sessionData?.chargerName || chargerId,
        time: util.formatTime(new Date(), 'MM-DD HH:mm')
      });
      // 最多保留10条
      if (history.length > 10) history = history.slice(0, 10);
      wx.setStorageSync('scanHistory', history);
    } catch (e) {
      // ignore
    }
  }
});
