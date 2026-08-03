// utils/util.js - 工具函数

/**
 * 格式化时间
 * @param {number|string|Date} date - 日期
 * @param {string} format - 格式 (默认 'YYYY-MM-DD HH:mm:ss')
 */
function formatTime(date, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!date) return '';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '';

  const year = d.getFullYear();
  const month = padZero(d.getMonth() + 1);
  const day = padZero(d.getDate());
  const hour = padZero(d.getHours());
  const minute = padZero(d.getMinutes());
  const second = padZero(d.getSeconds());

  return format
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hour)
    .replace('mm', minute)
    .replace('ss', second);
}

/**
 * 格式化时长（分钟 → X小时X分钟）
 * @param {number} minutes - 分钟数
 */
function formatDuration(minutes) {
  if (!minutes || minutes <= 0) return '0分钟';
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  if (h > 0 && m > 0) return `${h}小时${m}分钟`;
  if (h > 0) return `${h}小时`;
  return `${m}分钟`;
}

/**
 * 格式化金额（分 → 元）
 * @param {number} cents - 金额（分）
 */
function formatMoney(cents) {
  if (cents === null || cents === undefined) return '0.00';
  return (cents / 100).toFixed(2);
}

/**
 * 格式化金额（元，带符号）
 * @param {number} amount - 金额（元）
 */
function formatPrice(amount) {
  if (amount === null || amount === undefined) return '¥0.00';
  return `¥${Number(amount).toFixed(2)}`;
}

/**
 * 计算两点距离（Haversine公式）
 * @param {number} lat1 - 纬度1
 * @param {number} lng1 - 经度1
 * @param {number} lat2 - 纬度2
 * @param {number} lng2 - 经度2
 * @returns {number} 距离（公里）
 */
function calcDistance(lat1, lng1, lat2, lng2) {
  const R = 6371; // 地球半径（公里）
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * 格式化距离显示
 * @param {number} km - 距离（公里）
 */
function formatDistance(km) {
  if (km === null || km === undefined) return '未知';
  if (km < 1) return `${Math.round(km * 1000)}m`;
  return `${km.toFixed(1)}km`;
}

/**
 * 格式化电量（kWh）
 * @param {number} kwh - 电量
 */
function formatPower(kwh) {
  if (kwh === null || kwh === undefined) return '0 kWh';
  return `${Number(kwh).toFixed(2)} kWh`;
}

/**
 * 手机号脱敏
 * @param {string} phone - 手机号
 */
function maskPhone(phone) {
  if (!phone || phone.length !== 11) return phone;
  return phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
}

/**
 * 生成唯一ID
 */
function generateId() {
  return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 防抖
 * @param {Function} fn - 函数
 * @param {number} delay - 延迟（毫秒）
 */
function debounce(fn, delay = 300) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * 节流
 * @param {Function} fn - 函数
 * @param {number} interval - 间隔（毫秒）
 */
function throttle(fn, interval = 300) {
  let last = 0;
  return function (...args) {
    const now = Date.now();
    if (now - last >= interval) {
      last = now;
      fn.apply(this, args);
    }
  };
}

// 内部辅助
function padZero(n) {
  return n < 10 ? '0' + n : String(n);
}

function toRad(deg) {
  return deg * (Math.PI / 180);
}

module.exports = {
  formatTime,
  formatDuration,
  formatMoney,
  formatPrice,
  calcDistance,
  formatDistance,
  formatPower,
  maskPhone,
  generateId,
  debounce,
  throttle
};
