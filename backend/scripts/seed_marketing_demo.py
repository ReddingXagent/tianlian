#!/usr/bin/env python3
"""
营销演示种子数据注入(幂等) — 卡 a5e145d2

走 HTTP API 注入生产 http://demo.example.com , 三模块:
  - 折扣:   4 方案(覆盖启用/停用/生效中/已过期/未生效) + 3 折扣组
  - 优惠券: 4 模板(各态) + 2 发放批次(distribute 扣库存+生成券码) + 1 张核销(ACTIVE→USED)
  - 积分:   4 规则(各态) + 6 条流水(覆盖 earn/redeem/adjust/expire)

幂等(重复运行安全):
  - 折扣方案/折扣组/优惠券/积分规则: 按 name 查同名, 已存在则跳过(并复用其 id)
  - 发放批次: 按 (coupon_id, batch_name) 查重, 已有则跳过 distribute
  - 核销: 该券下已有 USED 态记录则跳过, 否则取一张 ACTIVE 核销
  - 积分流水: description 内嵌唯一标记 [SEED:A5E145D2:xxx], list 后按标记去重

只 INSERT 营销演示数据, 不动既有业务数据。独立运行:

    python scripts/seed_marketing_demo.py
    python scripts/seed_marketing_demo.py --base http://demo.example.com
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://demo.example.com"
API_PREFIX = "/api/v1"
LOGIN_USER = "mobile_test"
LOGIN_PASS = "Tianlian2026!"
SEED_TAG = "A5E145D2"  # 种子幂等标记, 内嵌于批次名/流水 description


# ── HTTP 工具 ──

def http(method, base, path, token=None, data=None, form=False, timeout=20):
    """同步 HTTP 调用, 返回 (status, body_json)。非 2xx 不抛, 由调用方判契约错位。"""
    url = base + API_PREFIX + path
    body = None
    headers = {}
    if form:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:500]}
    except Exception as e:  # 网络层错误
        return 0, {"error": f"{type(e).__name__}: {e}"}


def login(base):
    st, body = http("POST", base, "/auth/login",
                    data={"username": LOGIN_USER, "password": LOGIN_PASS}, form=True)
    assert st == 200 and body.get("data", {}).get("token"), \
        f"[FAIL] 登录失败 status={st} body={body}"
    token = body["data"]["token"]
    user = body["data"].get("user", {})
    print(f"[OK] 登录成功 user={user.get('username')} role={user.get('role')} "
          f"id={user.get('id')}")
    return token


def ok(status):
    return 200 <= status < 300


def iso(year, month, day, hour=0, minute=0):
    """naive ISO 串(与测试 payload 风格一致, Pydantic 接受)。"""
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"


# ── 通用幂等 helper ──

def list_items(base, token, path, params=None):
    """GET 分页(演示数据量小, page_size=100 一页足够), 返回 data.items 列表。"""
    qs = "?page=1&page_size=100"
    if params:
        qs += "&" + urllib.parse.urlencode(params)
    st, body = http("GET", base, path + qs, token=token)
    if not ok(st):
        print(f"  [WARN] list {path} status={st} body={body}")
        return []
    data = body.get("data", {})
    return data.get("items", []) if isinstance(data, dict) else []


def find_by_name(items, name):
    return next((i for i in items if i.get("name") == name), None)


# ── 折扣 ──

def seed_discounts(base, token):
    print("\n=== 折扣方案 ===")
    plans = [
        {  # 1. 启用·生效中
            "name": "新用户首单8.5折", "discount_type": "percentage", "discount_rate": 0.85,
            "applicable_user_types": "app", "min_consumption": 0,
            "start_time": iso(2026, 7, 1), "end_time": iso(2026, 12, 31),
            "priority": 10, "is_active": True, "description": "APP新用户首单立享8.5折",
        },
        {  # 2. 启用·生效中·有门槛
            "name": "企业客户阶梯优惠", "discount_type": "tiered", "discount_rate": 0.90,
            "applicable_user_types": "enterprise", "min_consumption": 1000,
            "max_discount_amount": 200,
            "start_time": iso(2026, 6, 1), "end_time": iso(2027, 6, 30),
            "priority": 20, "is_active": True, "description": "企业月度消费满1000元享9折,封顶200元",
        },
        {  # 3. 停用·已过期
            "name": "春节限时7折活动", "discount_type": "percentage", "discount_rate": 0.70,
            "applicable_user_types": "app,card,vin,interconnect,enterprise", "min_consumption": 0,
            "start_time": iso(2026, 1, 25), "end_time": iso(2026, 2, 10),
            "priority": 50, "is_active": False, "description": "春节活动(已结束归档)",
        },
        {  # 4. 启用·未生效
            "name": "冬夜充电9.5折(预热)", "discount_type": "percentage", "discount_rate": 0.95,
            "applicable_user_types": "app,card", "min_consumption": 0,
            "start_time": iso(2026, 12, 1), "end_time": iso(2027, 2, 28),
            "priority": 5, "is_active": True, "description": "冬季夜间充电优惠,12月生效",
        },
    ]
    ids = {}
    existing = list_items(base, token, "/operate/discount")
    for p in plans:
        hit = find_by_name(existing, p["name"])
        if hit:
            ids[p["name"]] = hit["id"]
            print(f"  [SKIP] 折扣方案已存在 id={hit['id']} name={p['name']}")
            continue
        st, body = http("POST", base, "/operate/discount", token=token, data=p)
        if ok(st):
            ids[p["name"]] = body["data"]["id"]
            print(f"  [NEW ] 折扣方案 id={body['data']['id']} name={p['name']}")
        else:
            print(f"  [FAIL] 折扣方案 name={p['name']} status={st} body={body}")
    return ids


def seed_discount_groups(base, token, ids):
    print("\n=== 折扣组 ===")
    groups = [
        {"name": "新用户专享组", "discount_id": ids["新用户首单8.5折"],
         "user_type": "app", "user_ids": "22", "station_ids": "", "priority": 10, "is_active": True},
        {"name": "企业VIP客户组", "discount_id": ids["企业客户阶梯优惠"],
         "user_type": "enterprise", "user_ids": "", "station_ids": "", "priority": 20, "is_active": True},
        {"name": "春节活动归档组", "discount_id": ids["春节限时7折活动"],
         "user_type": "app", "user_ids": "", "station_ids": "", "priority": 50, "is_active": False},
    ]
    existing = list_items(base, token, "/operate/discount/groups")
    for g in groups:
        if find_by_name(existing, g["name"]):
            print(f"  [SKIP] 折扣组已存在 name={g['name']}")
            continue
        st, body = http("POST", base, "/operate/discount/group", token=token, data=g)
        if ok(st):
            print(f"  [NEW ] 折扣组 id={body['data']['id']} name={g['name']}")
        else:
            print(f"  [FAIL] 折扣组 name={g['name']} status={st} body={body}")


# ── 优惠券 ──

def seed_coupons(base, token):
    print("\n=== 优惠券模板 ===")
    coupons = [
        {  # 1. 固定金额·启用·生效中
            "name": "新人立减20元券", "coupon_type": "fixed", "face_value": 20,
            "min_order_amount": 50, "total_stock": 1000, "per_user_limit": 1,
            "valid_days": 30, "start_time": iso(2026, 8, 1), "end_time": iso(2026, 9, 30),
            "is_active": True, "description": "新用户满50元立减20元",
        },
        {  # 2. 百分比·启用·生效中
            "name": "满200打9折券", "coupon_type": "percentage", "face_value": 0.9,
            "min_order_amount": 200, "max_discount_amount": 50, "total_stock": 500,
            "per_user_limit": 1, "valid_days": 15,
            "start_time": iso(2026, 8, 1), "end_time": iso(2026, 10, 31),
            "is_active": True, "description": "满200元享9折,封顶50元",
        },
        {  # 3. 免单·停用·已过期
            "name": "国庆免单券(已结束)", "coupon_type": "free_charge", "face_value": 0,
            "min_order_amount": 0, "total_stock": 100, "per_user_limit": 1, "valid_days": 7,
            "start_time": iso(2026, 9, 25), "end_time": iso(2026, 10, 8),
            "is_active": False, "description": "国庆免单活动(已结束)",
        },
        {  # 4. 免服务费·启用·未生效
            "name": "周年庆免服务费券(预热)", "coupon_type": "service_free", "face_value": 15,
            "min_order_amount": 0, "total_stock": 2000, "per_user_limit": 1, "valid_days": 30,
            "start_time": iso(2026, 10, 15), "end_time": iso(2026, 11, 15),
            "is_active": True, "description": "周年庆活动,10月生效",
        },
    ]
    ids = {}
    existing = list_items(base, token, "/operate/coupon")
    for c in coupons:
        hit = find_by_name(existing, c["name"])
        if hit:
            ids[c["name"]] = hit["id"]
            print(f"  [SKIP] 优惠券已存在 id={hit['id']} name={c['name']}")
            continue
        st, body = http("POST", base, "/operate/coupon", token=token, data=c)
        if ok(st):
            ids[c["name"]] = body["data"]["id"]
            print(f"  [NEW ] 优惠券 id={body['data']['id']} name={c['name']}")
        else:
            print(f"  [FAIL] 优惠券 name={c['name']} status={st} body={body}")
    return ids


def seed_coupon_batches(base, token, ids):
    """发放批次: distribute 扣库存+生成券码。按 (coupon_id, batch_name) 幂等。"""
    print("\n=== 优惠券发放批次 ===")
    target_coupon_id = ids["新人立减20元券"]
    pct_coupon_id = ids["满200打9折券"]
    batches = [
        {"coupon_id": target_coupon_id, "quantity": 3, "user_ids": "22",
         "user_type": "app", "batch_name": f"新人券-首批发放[{SEED_TAG}]"},
        {"coupon_id": pct_coupon_id, "quantity": 2, "user_ids": "22",
         "user_type": "app", "batch_name": f"秋季促销-9折券发放[{SEED_TAG}]"},
    ]
    for b in batches:
        existing = list_items(base, token, "/operate/coupon/batches",
                              params={"coupon_id": b["coupon_id"]})
        if any(x.get("batch_name") == b["batch_name"] for x in existing):
            print(f"  [SKIP] 发放批次已存在 batch_name={b['batch_name']}")
            continue
        st, body = http("POST", base, "/operate/coupon/distribute", token=token, data=b)
        if ok(st):
            d = body["data"]
            print(f"  [NEW ] 发放批次 batch_id={d.get('batch_id')} count={d.get('count')} "
                  f"name={b['batch_name']}")
        else:
            print(f"  [FAIL] 发放批次 name={b['batch_name']} status={st} body={body}")


def seed_coupon_redeem(base, token, ids):
    """核销一张新人券(ACTIVE→USED), 产生 USED 态演示数据。幂等: 已有 USED 则跳过。"""
    print("\n=== 优惠券核销(演示USED态) ===")
    coupon_id = ids["新人立减20元券"]
    usages = list_items(base, token, "/operate/coupon/usages", params={"user_id": 22})
    mine = [u for u in usages if u.get("coupon_id") == coupon_id]
    if any(u.get("status") == "used" for u in mine):
        print(f"  [SKIP] 该券已存在 USED 记录, 无需重复核销")
        return
    active = [u for u in mine if u.get("status") == "active"]
    if not active:
        print(f"  [WARN] 无可核销的 ACTIVE 券(可能库存/批次未就绪), 跳过核销")
        return
    code = active[0]["coupon_code"]
    st, body = http("POST", base, "/operate/coupon/redeem", token=token, data={
        "coupon_code": code, "order_id": 888888, "order_amount": 120,
    })
    if ok(st):
        print(f"  [NEW ] 核销成功 code={code} 抵扣={body['data'].get('discount_amount')}元")
    else:
        print(f"  [FAIL] 核销 code={code} status={st} body={body}")


# ── 积分 ──

def seed_points_rules(base, token):
    print("\n=== 积分规则 ===")
    rules = [
        {  # 1. 启用·生效中·充电
            "name": "充电消费送积分", "rule_type": "charge", "points": 1,
            "unit": "每消费1元送1分", "daily_limit": 500, "weekly_limit": 3000,
            "points_expire_days": 365, "is_active": True,
            "start_time": iso(2026, 1, 1), "end_time": iso(2027, 12, 31),
            "description": "充电消费按金额返积分",
        },
        {  # 2. 启用·签到
            "name": "每日签到奖励", "rule_type": "sign_in", "points": 10,
            "unit": "每次签到", "daily_limit": 1, "points_expire_days": 90,
            "is_active": True, "description": "每日签到得10积分",
        },
        {  # 3. 启用·限时活动
            "name": "充值双倍积分活动", "rule_type": "recharge", "points": 2,
            "unit": "每充值1元送2分", "points_expire_days": 180, "is_active": True,
            "start_time": iso(2026, 8, 1), "end_time": iso(2026, 8, 31),
            "description": "8月充值双倍积分限时活动",
        },
        {  # 4. 停用·已过期
            "name": "邀请好友奖励(已停用)", "rule_type": "invite", "points": 100,
            "unit": "每成功邀请1人", "total_limit": 5, "is_active": False,
            "start_time": iso(2026, 3, 1), "end_time": iso(2026, 6, 30),
            "description": "邀请好友奖励(活动已结束)",
        },
    ]
    ids = {}
    existing = list_items(base, token, "/operate/points")
    for r in rules:
        hit = find_by_name(existing, r["name"])
        if hit:
            ids[r["name"]] = hit["id"]
            print(f"  [SKIP] 积分规则已存在 id={hit['id']} name={r['name']}")
            continue
        st, body = http("POST", base, "/operate/points", token=token, data=r)
        if ok(st):
            ids[r["name"]] = body["data"]["id"]
            print(f"  [NEW ] 积分规则 id={body['data']['id']} name={r['name']}")
        else:
            print(f"  [FAIL] 积分规则 name={r['name']} status={st} body={body}")
    return ids


def seed_points_records(base, token, rule_ids):
    """积分流水(覆盖 earn/redeem/adjust/expire), 按 description 标记幂等。"""
    print("\n=== 积分流水 ===")
    USER = 22  # mobile_test
    flows = [
        {"user_id": USER, "record_type": "earn", "points": 50,
         "rule_id": rule_ids.get("充电消费送积分"), "balance_before": 0,
         "description": f"充电订单积分奖励 [SEED:{SEED_TAG}:earn-charge]"},
        {"user_id": USER, "record_type": "earn", "points": 10,
         "rule_id": rule_ids.get("每日签到奖励"), "balance_before": 50,
         "description": f"每日签到 [SEED:{SEED_TAG}:earn-signin]"},
        {"user_id": USER, "record_type": "earn", "points": 100,
         "rule_id": rule_ids.get("邀请好友奖励(已停用)"), "balance_before": 60,
         "description": f"邀请好友注册奖励 [SEED:{SEED_TAG}:earn-invite]"},
        {"user_id": USER, "record_type": "redeem", "points": -30,
         "balance_before": 160, "description": f"积分兑换充电抵扣 [SEED:{SEED_TAG}:redeem]"},
        {"user_id": USER, "record_type": "adjust", "points": 20,
         "balance_before": 130, "description": f"运营活动补发积分 [SEED:{SEED_TAG}:adjust]"},
        {"user_id": USER, "record_type": "expire", "points": -10,
         "balance_before": 150, "description": f"积分过期清零 [SEED:{SEED_TAG}:expire]"},
    ]
    existing = list_items(base, token, "/operate/points/records", params={"user_id": USER})
    seeded_tags = {x.get("description", "") for x in existing}
    for f in flows:
        if f["description"] in seeded_tags:
            print(f"  [SKIP] 积分流水已存在 tag={f['description'].split(']')[0]}]")
            continue
        st, body = http("POST", base, "/operate/points/records", token=token, data=f)
        if ok(st):
            print(f"  [NEW ] 积分流水 id={body['data']['id']} "
                  f"type={f['record_type']} points={f['points']}")
        else:
            print(f"  [FAIL] 积分流水 type={f['record_type']} status={st} body={body}")


# ── 汇总 ──

def summary(base, token, ids):
    print("\n=== 注入结果汇总 ===")
    d_total = list_items(base, token, "/operate/discount")
    g_total = list_items(base, token, "/operate/discount/groups")
    print(f"  折扣方案 list total={len(d_total)} | 折扣组 total={len(g_total)}")

    st, cbody = http("GET", base, "/operate/coupon/stats", token=token)
    if ok(st):
        cs = cbody["data"]
        print(f"  优惠券 stats: 模板={cs['total_coupons']} 总库存={cs['total_stock']} "
              f"已发放={cs['total_distributed']} 已使用={cs['total_used']} 核销率={cs['usage_rate']}%")

    st, pbody = http("GET", base, "/operate/points/stats", token=token)
    if ok(st):
        ps = pbody["data"]
        print(f"  积分 stats: 规则={ps['total_rules']} 启用={ps['active_rules']} "
              f"累计发放={ps['total_earned']} 流水={ps['total_records']}")


def main():
    parser = argparse.ArgumentParser(description="营销演示种子数据注入(幂等)")
    parser.add_argument("--base", default=DEFAULT_BASE, help="目标环境根地址")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"目标环境: {base}")
    token = login(base)
    did = seed_discounts(base, token)
    seed_discount_groups(base, token, did)
    cid = seed_coupons(base, token)
    seed_coupon_batches(base, token, cid)
    seed_coupon_redeem(base, token, cid)
    pid = seed_points_rules(base, token)
    seed_points_records(base, token, pid)
    summary(base, token, {"discount": did, "coupon": cid, "points": pid})
    print("\n[DONE] 营销演示种子注入完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
