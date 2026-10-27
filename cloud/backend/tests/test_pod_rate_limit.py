"""Pod/Cross 通信端点 IP 限流测试 (卡 d59fdbd5 D2加固)

生产场景: 固定外网IP每30s穷举 X-Pod-Secret (全部403)。verify_pod_comm_secret
只鉴权不限流, 需 per-real-IP 限流拦高频扫描。复用登录限流同款 slowapi 机制
(key_func=get_real_ip 读 XFF 首段), 阈值 60/min (合法心跳 2/min, 余量充足)。

覆盖:
  ① 10 个通信端点 (pod register/heartbeat/routes/stations/health/list/info
     + cross query/internal_query/routes) 均接路由级 limit_pod_comm(60/min):
     同 IP 前 60 次放行, 第 61 次 429
  ② 鉴权失败(403)与正常请求共享同一 IP 限额 — 错误 secret 穷举前 60 次 403, 第 61 次 429
  ③ XFF 独立计数: 不同 X-Forwarded-For 各自 60/min, 防伪造绕过
"""
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter

_POD_SECRET = "test-pod-comm-secret"


@pytest.fixture(autouse=True)
def _enable_rate_limit(client: TestClient, monkeypatch):
    """conftest 默认 RATE_LIMIT_ENABLED=false 关限流; 本文件每测例临时开启 limiter
    并 reset 内存计数 (limit_pod_comm 复用全局 limiter 的 storage/key_func)。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", _POD_SECRET)
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    yield


# (method, path, body) — 任务指定的 7 个通信端点
_ENDPOINTS = [
    ("post", "/api/v1/pod/register",
     {"pod_id": "pod-01", "region_id": "r1", "endpoint": "http://1.1.1.1", "version": "3.0.0"}),
    ("post", "/api/v1/pod/heartbeat", {"pod_id": "pod-01"}),
    ("get",  "/api/v1/pod/routes", None),
    ("get",  "/api/v1/pod/stations", None),
    # 卡 71eb08a7: health/list/info 补齐 limit_pod_comm, 与其余 pod 端点同 60/min
    ("get",  "/api/v1/pod/health", None),
    ("get",  "/api/v1/pod/list", None),
    ("get",  "/api/v1/pod/info/pod-01", None),
    ("post", "/api/v1/cross/query", {"station_ids": [1], "query_type": "overview"}),
    ("post", "/api/v1/cross/internal/query", {"station_ids": [1], "query_type": "overview"}),
    ("post", "/api/v1/cross/routes", {"station_ids": [1]}),
]


@pytest.mark.parametrize("method,path,body", _ENDPOINTS)
def test_comm_endpoint_rate_limited_60_per_min(client, method, path, body):
    """① 每个通信端点 60/min per real IP: 前 60 次放行(非429), 第 61 次 429。"""
    headers = {"X-Pod-Secret": _POD_SECRET, "X-Forwarded-For": "10.0.0.1"}
    codes = []
    for _ in range(61):
        r = client.request(method, path, json=body, headers=headers)
        codes.append(r.status_code)
    assert 429 not in codes[:60], (
        f"{path} 前60次不应限流, 出现429: {[i for i,c in enumerate(codes[:60]) if c==429]}")
    assert codes[60] == 429, f"{path} 第61次应429, 实际 {codes[60]}"


def test_auth_failure_counts_toward_limit(client):
    """② 鉴权失败(403)也计数: 错误 secret 穷举 /cross/routes, 前60次403, 第61次429。

    limit_pod_comm 作为路由级 dependency 先于 verify_pod_comm_secret 执行
    (FastAPI route dependencies 先于端点参数依赖), 故 403 与 200 共享同一 IP 计数 —
    正是拦穷举所需 (生产场景固定外网IP穷举全403, 若限流落后于鉴权则永不触发)。
    """
    headers = {"X-Pod-Secret": "WRONG-SECRET", "X-Forwarded-For": "10.0.0.2"}
    codes = []
    for _ in range(61):
        r = client.post("/api/v1/cross/routes", json={"station_ids": [1]}, headers=headers)
        codes.append(r.status_code)
    assert all(c == 403 for c in codes[:60]), f"前60次应403(穷举鉴权失败), 实际前5: {codes[:5]}"
    assert codes[60] == 429, f"穷举第61次应429, 实际 {codes[60]}"


def test_xff_ips_have_independent_limits(client):
    """③ XFF 独立计数: IP-A 打满60次后第61次429; IP-B 第1次仍放行(非429)。

    key_func=get_real_ip 读 X-Forwarded-For 首段, 不同真实 IP 独立计数, 防伪造绕过。
    """
    body = {"pod_id": "pod-01"}
    headers_a = {"X-Pod-Secret": _POD_SECRET, "X-Forwarded-For": "10.0.0.3"}
    headers_b = {"X-Pod-Secret": _POD_SECRET, "X-Forwarded-For": "10.0.0.4"}
    for _ in range(60):
        client.post("/api/v1/pod/heartbeat", json=body, headers=headers_a)
    r_a = client.post("/api/v1/pod/heartbeat", json=body, headers=headers_a)
    assert r_a.status_code == 429, f"IP-A 第61次应429, 实际 {r_a.status_code}"
    r_b = client.post("/api/v1/pod/heartbeat", json=body, headers=headers_b)
    assert r_b.status_code != 429, f"IP-B 第1次应放行, 实际 {r_b.status_code} — 限流key未按XFF区分IP"
