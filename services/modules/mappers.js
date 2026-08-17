// services/modules/mappers.js - 归一化层 (后端snake_case → 前端camelCase)

const ORDER_STATUS_TO_UI = { charging: 'charging', settled: 'pending', paid: 'finished' };
const ORDER_STATUS_TO_BACKEND = { charging: 'charging', pending: 'settled', finished: 'paid' };
const COUPON_STATUS_TO_BACKEND = { unused: 'active', used: 'used', expired: 'expired' };

function mapOrder(o) {
  if (!o) return o;
  return {
    id: String(o.id),
    sessionId: String(o.id),
    orderNo: o.order_no,
    stationId: o.station_id,
    deviceId: o.device_id,
    userId: o.user_id,
    status: ORDER_STATUS_TO_UI[o.status] || o.status,
    rawStatus: o.status,
    energyKwh: o.energy_kwh,
    durationMin: o.duration_min,
    amount: o.amount,
    discountAmount: o.discount_amount,
    finalAmount: o.final_amount,
    pointsEarned: o.points_earned,
    paidAt: o.paid_at
  };
}

function mapCoupon(c) {
  if (!c) return c;
  return {
    id: String(c.id),
    code: c.code,
    name: c.name,
    type: c.coupon_type,
    value: c.value,
    minAmount: c.min_amount,
    status: c.status === 'active' ? 'unused' : c.status,
    rawStatus: c.status,
    expireAt: c.expire_at
  };
}

function mapPoints(p) {
  if (!p) return p;
  return {
    userId: p.user_id,
    balance: p.balance,
    history: (p.recent || []).map((r) => ({
      delta: r.delta,
      reason: r.reason,
      createdAt: r.created_at
    }))
  };
}

function mapPagination(d, mapper) {
  return {
    items: (d.items || []).map(mapper),
    total: d.total || 0,
    page: d.page || 1,
    pageSize: d.page_size || 20
  };
}

module.exports = {
  mapOrder,
  mapCoupon,
  mapPoints,
  mapPagination,
  ORDER_STATUS_TO_UI,
  ORDER_STATUS_TO_BACKEND,
  COUPON_STATUS_TO_BACKEND
};
