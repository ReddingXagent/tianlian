// services/modules/favorites.js - 收藏接口 (后端暂无, 本地存储降级)

function getFavorites() {
  return Promise.resolve({ code: 200, data: wx.getStorageSync('favorites') || [] });
}

function addFavorite(stationId) {
  const favs = wx.getStorageSync('favorites') || [];
  if (!favs.includes(stationId)) {
    favs.push(stationId);
    wx.setStorageSync('favorites', favs);
  }
  return Promise.resolve({ code: 200, data: { stationId } });
}

function removeFavorite(stationId) {
  const favs = (wx.getStorageSync('favorites') || []).filter((id) => id !== stationId);
  wx.setStorageSync('favorites', favs);
  return Promise.resolve({ code: 200, data: { stationId } });
}

module.exports = { getFavorites, addFavorite, removeFavorite };
