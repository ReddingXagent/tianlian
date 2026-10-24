"""
cross_pod.py 覆盖率补充测试 (卡片 d79b2bbd)

补原 tests/test_cross_pod.py 未触及的分支:
- query_type=stats 本地统计查询           (L243-263)
- 本地查询异常捕获                        (L101-107)
- 远程查询块: Pod未注册/endpoint缺失/远程成功/远程异常 (L111-156)
- query_remote HTTP 调用: 成功/超时/HTTP错误/其他异常 (L290-319)

注: L145-152 (远程 Pod 查询异常分支) 原 bug 已修复 [5856bad4] ——
    remote_tasks[i] 是 coroutine 无 pod_id 属性, 改用并行 task_pod_ids 列表按索引取 pod_id。
    新增 test_cross_query_remote_pod_exception_isolated /
        test_cross_query_mixed_remote_one_fails_one_ok 覆盖该分支。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.api.v1.cross_pod as cross_pod_mod

# D2 (卡69acc93c): /cross 写端点强制 X-Pod-Secret 共享密钥。本文件合法用例注入
# 密钥配置 + 默认请求头; 反向 403 路径由 test_auth_gaps_d2.py 覆盖。
_POD_SECRET = "test-pod-comm-secret"


@pytest.fixture(autouse=True)
def _inject_pod_secret(monkeypatch, client):
    from app.core.config import settings
    monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", _POD_SECRET)
    client.headers["X-Pod-Secret"] = _POD_SECRET
    yield


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    """mock DNS 解析保证确定性(卡 bab27c02 起 query_remote 出站前校验 endpoint)。

    IP 字面量原样返回; 域名一律解析为公网 1.1.1.1。
    """
    import ipaddress
    import socket
    from app.core import url_safety

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            ip = "1.1.1.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


# ===== stats 查询类型 (L243-263) =====

def test_cross_query_stats_type_online(client, seed_stations, seed_devices):
    """stats 查询返回设备在线/离线/故障统计 (station_a 全 ONLINE)"""
    sid = seed_stations["station_a"].id  # INV001 + CHG001 均 ONLINE
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid], "query_type": "stats",
    })
    assert resp.status_code == 200
    r = resp.json()["results"][0]
    assert r["online_devices"] == 2
    assert r["offline_devices"] == 0
    assert r["fault_devices"] == 0
    assert r["total_devices"] == 2
    assert "health_score" in r


def test_cross_query_stats_type_fault_offline(client, seed_stations, seed_devices):
    """stats 查询正确区分 FAULT/OFFLINE (station_b: PCS=FAULT, OFF=OFFLINE)"""
    sid = seed_stations["station_b"].id
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid], "query_type": "stats",
    })
    assert resp.status_code == 200
    r = resp.json()["results"][0]
    assert r["online_devices"] == 0
    assert r["offline_devices"] == 1
    assert r["fault_devices"] == 1
    assert r["total_devices"] == 2


# ===== 本地查询异常捕获 (L101-107) =====

def test_cross_query_local_exception_collected(client, seed_stations, monkeypatch):
    """本地查询抛异常 → 错误进 errors, 不 500, results 为空 (L101-107)"""
    async def boom(*args, **kwargs):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(cross_pod_mod, "query_local", boom)

    sid = seed_stations["station_a"].id
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert len(body["errors"]) == 1
    err = body["errors"][0]
    assert "db exploded" not in err["error"]  # 安全: 不得泄露内部异常原文
    assert err["error"]  # 仍提供通用错误描述
    assert err["pod_id"]  # 本地 pod-01
    assert err["station_ids"]  # 序列化的本地 station_ids


# ===== 远程查询块 (L111-156) =====
# 触发条件: station_router.local_only=False 且存在非本地 Pod 的场站

class _FakeRouter:
    """多 Pod 路由器替身: local_only=False, route_station/get_pod_info 可控"""

    local_only = False
    pod_id = "pod-01"

    def __init__(self, routes, pod_registry):
        # routes: sid -> {"pod_id": ...}
        # pod_registry: pod_id -> info dict (含 endpoint) 或 None
        self._routes = routes
        self._pod_registry = pod_registry

    def route_station(self, sid):
        return self._routes.get(sid, {"pod_id": "pod-01"})

    def get_pod_info(self, pod_id):
        return self._pod_registry.get(pod_id)


def _install_multi_pod_router(monkeypatch, routes, pod_registry):
    """把 cross_pod 模块的 get_station_router 替换成多 Pod 路由器"""
    monkeypatch.setattr(
        cross_pod_mod, "get_station_router",
        lambda: _FakeRouter(routes, pod_registry),
    )


def test_cross_query_remote_pod_unregistered(client, seed_stations, monkeypatch):
    """远程 Pod 未注册 (get_pod_info=None) → 错误进 errors (L119-125)"""
    sid = seed_stations["station_a"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={sid: {"pod_id": "pod-02"}},
        pod_registry={"pod-02": None},  # pod-02 未注册
    )
    resp = client.post("/api/v1/cross/query", json={"station_ids": [sid]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert any("未注册" in e["error"] for e in body["errors"])


def test_cross_query_remote_pod_no_endpoint(client, seed_stations, monkeypatch):
    """远程 Pod endpoint 为空 → 错误进 errors (L128-134)"""
    sid = seed_stations["station_a"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={sid: {"pod_id": "pod-02"}},
        pod_registry={"pod-02": {"pod_id": "pod-02", "endpoint": ""}},
    )
    resp = client.post("/api/v1/cross/query", json={"station_ids": [sid]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert any("endpoint" in e["error"] for e in body["errors"])


def test_cross_query_remote_success(client, seed_stations, monkeypatch):
    """远程 Pod 查询成功 → 结果合并进 results, 无 error (L136-138, 141-156)"""
    sid = seed_stations["station_a"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={sid: {"pod_id": "pod-02"}},
        pod_registry={"pod-02": {"pod_id": "pod-02", "endpoint": "http://pod-02:8000"}},
    )

    captured = {}

    async def fake_remote(endpoint, station_ids, query_type, include_details, pod_id):
        captured["endpoint"] = endpoint
        captured["pod_id"] = pod_id
        captured["station_ids"] = list(station_ids)
        return {
            "pod_id": pod_id,
            "results": [{"station_id": s, "name": f"remote-{s}"} for s in station_ids],
        }
    monkeypatch.setattr(cross_pod_mod, "query_remote", fake_remote)

    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    # 透传给 query_remote 的参数
    assert captured["endpoint"] == "http://pod-02:8000"
    assert captured["pod_id"] == "pod-02"
    assert captured["station_ids"] == [sid]
    # sid 路由到 pod-02, 本地 pod-01 无场站 → results 全来自远程
    assert len(body["results"]) == 1
    assert body["results"][0]["station_id"] == sid
    assert body["errors"] == []
    assert body["pods_involved"] == ["pod-02"]


def test_cross_query_mixed_local_and_remote(client, seed_stations, monkeypatch):
    """混合: 一场站本地 pod-01, 一场站远程 pod-02 → 两边结果都返回"""
    local_sid = seed_stations["station_a"].id
    remote_sid = seed_stations["station_b"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={
            local_sid: {"pod_id": "pod-01"},
            remote_sid: {"pod_id": "pod-02"},
        },
        pod_registry={"pod-02": {"pod_id": "pod-02", "endpoint": "http://pod-02:8000"}},
    )

    async def fake_remote(endpoint, station_ids, query_type, include_details, pod_id):
        return {
            "pod_id": pod_id,
            "results": [{"station_id": station_ids[0], "remote": True}],
        }
    monkeypatch.setattr(cross_pod_mod, "query_remote", fake_remote)

    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [local_sid, remote_sid], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    # 按 pod 分组: pod-01 先入字典, pod-02 后入
    assert body["pods_involved"] == ["pod-01", "pod-02"]
    # 本地 station_a 概览 + 远程 station_b 结果
    returned_sids = sorted(r["station_id"] for r in body["results"])
    assert returned_sids == sorted([local_sid, remote_sid])
    assert body["errors"] == []


# ===== query_remote 直接单测 (L290-319) =====

async def test_query_remote_success_marks_pod_id():
    """query_remote 成功: POST 远程, 给每个 result 标记 pod_id (L290-312)"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"station_id": 1}, {"station_id": 2}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await cross_pod_mod.query_remote(
            "http://pod-02:8000", [1, 2], "overview", False, "pod-02"
        )

    assert result["pod_id"] == "pod-02"
    assert len(result["results"]) == 2
    for r in result["results"]:
        assert r["pod_id"] == "pod-02"  # 标记了来源 Pod
    # 请求 URL 与 payload
    call_args = mock_instance.post.call_args
    assert call_args[0][0] == "http://pod-02:8000/api/v1/cross/query"
    assert call_args[1]["json"] == {
        "station_ids": [1, 2], "query_type": "overview", "include_details": False,
    }


async def test_query_remote_sends_pod_secret_header(monkeypatch):
    """卡 69acc93c: query_remote 作为 Pod 间 RPC 客户端须携带 X-Pod-Secret 自证,
    否则远程 /cross/query 共享密钥校验会 403, 多 Pod 聚合查询断链。"""
    from app.core.config import settings
    from app.core.pod_security import POD_SECRET_HEADER

    monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", "rpc-secret-d2")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"station_id": 1}]}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance
        await cross_pod_mod.query_remote(
            "http://pod-02:8000", [1], "overview", False, "pod-02"
        )
    sent_headers = mock_instance.post.call_args[1]["headers"]
    assert sent_headers[POD_SECRET_HEADER] == "rpc-secret-d2"


async def test_query_remote_success_empty_results():
    """远程返回无 results 键 → data.get 兜底返回空列表 (L306, L311)"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"unrelated": "payload"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await cross_pod_mod.query_remote(
            "http://ep", [9], "stats", True, "pod-99"
        )
    assert result["pod_id"] == "pod-99"
    assert result["results"] == []


async def test_query_remote_timeout_raises():
    """httpx 超时 → 抛 Exception 含 '超时' (L314-315)"""
    import httpx
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("read timeout")
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception, match="超时"):
            await cross_pod_mod.query_remote("http://ep", [1], "overview", False, "pod-02")


async def test_query_remote_http_status_error_raises():
    """httpx HTTP 错误状态 → 抛 Exception 含状态码 (L316-317)"""
    import httpx
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    http_err = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_resp
    )
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = http_err
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception, match="503"):
            await cross_pod_mod.query_remote("http://ep", [1], "overview", False, "pod-02")


async def test_query_remote_generic_exception_raises():
    """其他异常 → 抛 Exception 含 '请求失败' (L318-319)"""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = ConnectionError("network unreachable")
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception, match="请求失败"):
            await cross_pod_mod.query_remote("http://ep", [1], "overview", False, "pod-02")


# ===== 远程 Pod 查询异常隔离 (L145-152) =====
# 原 bug: remote_tasks[i] 是 coroutine 无 pod_id 属性, 远程查询失败即 AttributeError → 整体 500
# 修复 [5856bad4]: 并行 task_pod_ids 列表按索引取 pod_id, 单 Pod 失败仅标记 error 不影响整体

def test_cross_query_remote_pod_exception_isolated(client, seed_stations, monkeypatch):
    """单个远程 Pod 查询抛异常 → 该 Pod 进 errors, 整体 200, results 为空 (L145-152)"""
    sid = seed_stations["station_a"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={sid: {"pod_id": "pod-02"}},
        pod_registry={"pod-02": {"pod_id": "pod-02", "endpoint": "http://pod-02:8000"}},
    )

    async def boom_remote(endpoint, station_ids, query_type, include_details, pod_id):
        raise RuntimeError("pod-02 unreachable")
    monkeypatch.setattr(cross_pod_mod, "query_remote", boom_remote)

    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert len(body["errors"]) == 1
    err = body["errors"][0]
    assert err["pod_id"] == "pod-02"
    assert "pod-02 unreachable" in err["error"]


def test_cross_query_mixed_remote_one_fails_one_ok(client, seed_stations, monkeypatch):
    """两个远程 Pod: pod-02 失败、pod-03 成功 → 失败者进 errors, 成功者结果正常合并, 整体 200"""
    fail_sid = seed_stations["station_a"].id
    ok_sid = seed_stations["station_b"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={
            fail_sid: {"pod_id": "pod-02"},
            ok_sid: {"pod_id": "pod-03"},
        },
        pod_registry={
            "pod-02": {"pod_id": "pod-02", "endpoint": "http://pod-02:8000"},
            "pod-03": {"pod_id": "pod-03", "endpoint": "http://pod-03:8000"},
        },
    )

    async def selective_remote(endpoint, station_ids, query_type, include_details, pod_id):
        if pod_id == "pod-02":
            raise RuntimeError("pod-02 down")
        return {
            "pod_id": pod_id,
            "results": [{"station_id": station_ids[0], "remote": True}],
        }
    monkeypatch.setattr(cross_pod_mod, "query_remote", selective_remote)

    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [fail_sid, ok_sid], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    # pods 插入顺序由 request.station_ids 决定: pod-02(fail_sid 先) → pod-03
    assert body["pods_involved"] == ["pod-02", "pod-03"]
    # 成功 Pod 结果正常合并
    assert len(body["results"]) == 1
    assert body["results"][0]["station_id"] == ok_sid
    # 失败 Pod 进 errors, 不影响其他 Pod / 整体响应
    assert len(body["errors"]) == 1
    assert body["errors"][0]["pod_id"] == "pod-02"
    assert "pod-02 down" in body["errors"][0]["error"]


# ===== 卡 bab27c02: query_remote 出站前 SSRF 兜底校验 =====

async def test_query_remote_rejects_metadata_endpoint_before_request():
    """endpoint 指向云元数据 169.254.169.254 → 出站前抛 UnsafeURLError, 不发请求"""
    from app.core.url_safety import UnsafeURLError

    with patch("httpx.AsyncClient") as mock_client:
        with pytest.raises(UnsafeURLError, match="169.254.169.254"):
            await cross_pod_mod.query_remote(
                "http://169.254.169.254/latest/meta-data", [1], "overview", False, "pod-x"
            )
    mock_client.assert_not_called()  # 兜底校验先于任何网络调用


async def test_query_remote_rejects_loopback_endpoint_before_request():
    """endpoint 指向 127.0.0.1 → 出站前抛 UnsafeURLError, 不发请求"""
    from app.core.url_safety import UnsafeURLError

    with patch("httpx.AsyncClient") as mock_client:
        with pytest.raises(UnsafeURLError, match="127.0.0.1"):
            await cross_pod_mod.query_remote(
                "http://127.0.0.1:8000", [1], "overview", False, "pod-x"
            )
    mock_client.assert_not_called()


async def test_query_remote_rejects_private_net_endpoint_before_request():
    """endpoint 指向内网 10.x/192.168.x → 出站前抛 UnsafeURLError, 不发请求"""
    from app.core.url_safety import UnsafeURLError

    for bad in ("http://10.1.2.3:8000", "http://192.168.1.10:8000"):
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(UnsafeURLError):
                await cross_pod_mod.query_remote(bad, [1], "overview", False, "pod-x")
        mock_client.assert_not_called()


async def test_query_remote_rejects_file_scheme_before_request():
    """endpoint 为 file:// → 出站前抛 UnsafeURLError, 不发请求"""
    from app.core.url_safety import UnsafeURLError

    with patch("httpx.AsyncClient") as mock_client:
        with pytest.raises(UnsafeURLError, match="scheme"):
            await cross_pod_mod.query_remote(
                "file:///etc/passwd", [1], "overview", False, "pod-x"
            )
    mock_client.assert_not_called()


def test_cross_query_unsafe_remote_endpoint_isolated(client, seed_stations, monkeypatch):
    """Redis 注册表被污染写入内网 endpoint(绕过 register 侧校验) → 出站兜底拦截,
    错误进 errors 不 500, 其他 Pod 不受影响"""
    sid_a = seed_stations["station_a"].id
    sid_b = seed_stations["station_b"].id
    _install_multi_pod_router(
        monkeypatch,
        routes={
            sid_a: {"pod_id": "pod-evil"},
            sid_b: {"pod_id": "pod-ok"},
        },
        pod_registry={
            "pod-evil": {"pod_id": "pod-evil", "endpoint": "http://169.254.169.254/x"},
            "pod-ok": {"pod_id": "pod-ok", "endpoint": "http://pod-ok:8000"},
        },
    )

    async def only_ok_remote(endpoint, station_ids, query_type, include_details, pod_id):
        assert pod_id == "pod-ok"  # pod-evil 应在校验层抛掉, 到不了这里
        return {"pod_id": pod_id, "results": [{"station_id": station_ids[0]}]}

    monkeypatch.setattr(cross_pod_mod, "query_remote", only_ok_remote)
    # 但 pod-evil 的 UnsafeURLError 需真实 query_remote 才能触发 → 直接注入
    from app.core.url_safety import UnsafeURLError

    async def real_check_remote(endpoint, *args, **kwargs):
        from app.core.url_safety import validate_external_url
        validate_external_url(endpoint)  # pod-evil 在此抛 UnsafeURLError
        return await only_ok_remote(endpoint, *args, **kwargs)

    monkeypatch.setattr(cross_pod_mod, "query_remote", real_check_remote)

    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid_a, sid_b], "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 1  # 仅 pod-ok 的结果
    assert body["results"][0]["station_id"] == sid_b
    assert len(body["errors"]) == 1
    assert body["errors"][0]["pod_id"] == "pod-evil"
