// services/modules/auth.js - 认证接口 (对齐真后端 OAuth2 form-urlencoded)
const { request } = require('./client');

/**
 * 用户名密码登录 (后端 /auth/login 走 OAuth2PasswordRequestForm)
 * 登录成功自动落盘 token + userInfo
 */
function login(username, password) {
  return request('/auth/login', {
    method: 'POST',
    form: true,
    data: { username, password },
    showLoading: true,
    loadingText: '登录中...'
  }).then((res) => {
    const d = res.data || {};
    if (d.token) {
      wx.setStorageSync('token', d.token);
    }
    if (d.user) {
      wx.setStorageSync('userInfo', d.user);
    }
    return res;
  });
}

/** 微信登录 (后端暂无wx登录端点, 保留占位, 走用户名密码登录) */
function wxLogin() {
  return Promise.reject(new Error('请使用用户名密码登录'));
}

function logout() {
  wx.removeStorageSync('token');
  wx.removeStorageSync('userInfo');
}

function getCurrentUser() {
  return wx.getStorageSync('userInfo') || null;
}

function getCurrentUserId() {
  const u = getCurrentUser();
  return u && u.id !== undefined && u.id !== null ? u.id : null;
}

/**
 * 获取用户信息 → GET /auth/me (后端返回当前用户+权限列表)
 * 同时更新本地缓存
 */
function getUserInfo() {
  return request('/auth/me').then((res) => {
    if (res.data) {
      wx.setStorageSync('userInfo', res.data);
    }
    return res;
  });
}

/**
 * 更新用户信息 (后端暂无 PUT/PATCH 端点, 走本地缓存更新)
 */
function updateUserInfo(data) {
  const user = getCurrentUser();
  if (user) {
    const updated = { ...user, ...data };
    wx.setStorageSync('userInfo', updated);
    return Promise.resolve({ code: 200, data: updated });
  }
  return Promise.reject(new Error('未登录'));
}

module.exports = {
  login,
  wxLogin,
  logout,
  getCurrentUser,
  getCurrentUserId,
  getUserInfo,
  updateUserInfo
};
