// services/modules/wallet.js - 钱包接口 (后端暂无, 占位)

function getWallet() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

function recharge() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

function getTransactions() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

module.exports = { getWallet, recharge, getTransactions };
