// config/index.js - 全局配置

// 环境切换: 'dev' | 'staging' | 'prod'
const ENV = process.env.NODE_ENV === 'production' ? 'prod' : 'dev';

const ENV_CONFIG = {
  dev: {
    API_BASE_URL: 'http://localhost:8000/api/v1',
    MAP_KEY: 'YOUR_TENCENT_MAP_KEY'
  },
  staging: {
    API_BASE_URL: 'http://8.134.106.166:8000/api/v1',
    MAP_KEY: 'YOUR_TENCENT_MAP_KEY'
  },
  prod: {
    API_BASE_URL: 'http://8.134.106.166/api/v1',
    MAP_KEY: 'YOUR_TENCENT_MAP_KEY'
  }
};

module.exports = {
  // 环境
  ENV,

  // API 基础地址
  API_BASE_URL: ENV_CONFIG[ENV].API_BASE_URL,

  // 腾讯地图 KEY（需替换为实际key）
  MAP_KEY: ENV_CONFIG[ENV].MAP_KEY,

  // 请求超时（毫秒）
  REQUEST_TIMEOUT: 15000,

  // 充电状态轮询间隔（毫秒）
  CHARGING_POLL_INTERVAL: 3000,

  // API 缓存 TTL（毫秒）
  CACHE_TTL: {
    STATIONS: 60000,      // 站点列表 60s
    STATION_DETAIL: 30000, // 站点详情 30s
    FAVORITES: 30000,     // 收藏列表 30s
    COUPONS: 60000,       // 优惠券 60s
    POINTS: 30000,        // 积分 30s
    ORDERS: 10000,        // 订单 10s（需较新）
    NOTIFICATIONS: 15000, // 通知 15s
    USER_INFO: 120000     // 用户信息 120s
  },

  // 订单状态
  ORDER_STATUS: {
    CHARGING: 'charging',    // 充电中
    FINISHED: 'finished',    // 已完成
    CANCELLED: 'cancelled',  // 已取消
    PENDING: 'pending'       // 待支付
  },

  // 充电状态映射
  CHARGE_STATUS_MAP: {
    idle: '空闲',
    charging: '充电中',
    offline: '离线',
    fault: '故障'
  },

  // 优惠券状态
  COUPON_STATUS: {
    UNUSED: 'unused',        // 未使用
    USED: 'used',            // 已使用
    EXPIRED: 'expired'       // 已过期
  },

  // 优惠券类型
  COUPON_TYPE: {
    AMOUNT: 'amount',        // 满减券
    DISCOUNT: 'discount',    // 折扣券
    FREIGHT: 'freight'       // 免运券
  },

  // 积分规则
  POINTS_RULES: {
    SIGN_IN_DAILY: 5,        // 每日签到
    CHARGE_PER_YUAN: 1,      // 每消费1元
    INVITE_FRIEND: 50,       // 邀请好友
    REVIEW_ORDER: 10         // 评价订单
  },

  // 通知类型
  NOTIFICATION_TYPES: {
    CHARGE_FINISH: 'charge_finish',
    CHARGE_START: 'charge_start',
    PAYMENT_SUCCESS: 'payment_success',
    COUPON_EXPIRE: 'coupon_expire',
    SYSTEM: 'system',
    PROMOTION: 'promotion'
  },

  // 站点筛选条件
  STATION_FILTERS: {
    SORT_BY: {
      DISTANCE: 'distance',
      PRICE: 'price',
      RATING: 'rating'
    },
    GUN_TYPE: {
      AC: 'ac',
      DC: 'dc'
    }
  }
};