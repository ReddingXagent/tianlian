"""tests/api 共享测试 helper（普通函数，按需 import，非 fixture）。

提供跨测试文件复用的工具：身份切换、工单/Coupon/文章创建等。

设计原则：自包含、不污染根 conftest、不依赖真实生产 DB（复用 conftest.client 的
隔离临时库），每个 helper 显式断言前置条件，失败即给出可读上下文。
"""

# 工单路由前缀（注意带横线）
WO_URL = "/api/v1/work-orders"
# 优惠券路由前缀
COUPON_URL = "/api/v1/operate/coupon"
# 知识库路由前缀
KB_URL = "/api/v1/knowledge"


# ─── Coupon 发放窗口动态锚点 ───
# 发放路径 enforce start_time≤now≤end_time（卡 73d52e60）后，硬编码日期的券
# 会在 2027-01-01 起全部落入"已结束"被拒，测试随时间腐烂（卡 7b7a7444 教训）。
# 故默认锚点改为相对 now 的动态窗口。
def coupon_window(**offset_days):
    """返回相对当前时间的 (start_time, end_time) ISO 字符串元组。

    默认 [-30, +30] 天；用关键字覆盖，如 coupon_window(start=-1, end=1)。
    """
    from datetime import datetime, timedelta
    start_off = timedelta(days=offset_days.get("start", -30))
    end_off = timedelta(days=offset_days.get("end", 30))
    now = datetime.utcnow()
    return (
        (now + start_off).isoformat(),
        (now + end_off).isoformat(),
    )


def login_as(client, username: str, password: str) -> str:
    """登录指定用户，覆盖 client 的 Authorization 头，返回 token。

    用于权限测试：conftest.client 默认 admin 身份，调用本 helper 切到非 admin
    （如 engineer1/viewer1，由 seed_users fixture 预建）以验证 403/404。
    """
    client.headers.pop("Authorization", None)
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.status_code} {r.text[:200]}"
    token = r.json()["data"]["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


def login_admin(client) -> str:
    """切回 admin 身份（与 login_as 配对，用于同一 test 内多次切换）。"""
    return login_as(client, "admin", "admin123")


# ─── 工单 helper ───

def create_wo(client, **overrides) -> str:
    """通过 API（admin 身份）创建工单，返回工单 id。"""
    body = {"fault_desc": "测试工单", "type": "repair", "level": "warning"}
    body.update(overrides)
    r = client.post(WO_URL, json=body)
    assert r.status_code == 200, f"创建工单失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]["id"]


def advance_wo(client, wo_id: str, *steps: str) -> dict:
    """按顺序对工单执行状态推进动作（accept/start/complete/verify/reject）。

    每步格式 "action" 或 "action=arg"（如 complete=修好了、reject=不合格）。
    返回最后一步的响应 JSON。
    """
    last = {}
    for step in steps:
        if "=" in step:
            action, arg = step.split("=", 1)
            url = f"{WO_URL}/{wo_id}/{action}"
            if action in ("complete",):
                r = client.post(url, params={"solution": arg})
            elif action in ("reject",):
                r = client.post(url, params={"reason": arg})
            else:
                r = client.post(url)
        else:
            r = client.post(f"{WO_URL}/{wo_id}/{step}")
        assert r.status_code == 200, f"推进 {step} 失败: {r.status_code} {r.text[:300]}"
        last = r.json()
    return last


# ─── 优惠券 helper ───

def create_coupon(client, **overrides) -> int:
    """通过 API 创建优惠券（admin 身份），返回 coupon_id。默认发放窗口为当前时间前后 30 天。"""
    start_time, end_time = coupon_window()
    body = {
        "name": "测试优惠券",
        "coupon_type": "fixed",
        "face_value": 10.0,
        "total_stock": 100,
        "start_time": start_time,
        "end_time": end_time,
    }
    body.update(overrides)
    r = client.post(COUPON_URL, json=body)
    assert r.status_code == 200, f"创建优惠券失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]["id"]
