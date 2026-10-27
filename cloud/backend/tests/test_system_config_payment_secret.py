"""
系统配置 - 支付通道 api_secret 安全测试 (卡 74277557)

覆盖三缺口:
1. GET list 响应 api_secret 掩码非明文
2. 非 admin 且无 system:config 权限用户 GET → 403
3. PUT 掩码哨兵 api_secret 不覆盖已存明文; 显式明文可正常更新
"""
import pytest


def _login_as(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture
def viewer_token(client):
    """seed 一个 VIEWER 用户并登录, 供非 admin 403 测试 (无 system:config 权限)。"""
    import bcrypt
    from app.models.user import User, UserRole
    s = client._sesh
    if not s.query(User).filter(User.username == "payviewer").first():
        s.add(User(
            username="payviewer",
            password_hash=bcrypt.hashpw(b"payview123", bcrypt.gensalt()).decode(),
            role=UserRole.VIEWER,
            status="active",
        ))
        s.commit()
    return _login_as(client, "payviewer", "payview123")


SECRET = "real-secret-abcdef123456"


class TestSecretMasking:
    def test_list_masks_api_secret(self, client):
        """GET list 返回的 api_secret 为掩码, 非明文。"""
        client.post("/api/v1/system-config/payment-channels", json={
            "name": "IM-B支付", "channel_type": "im_b", "api_secret": SECRET,
        })
        items = client.get("/api/v1/system-config/payment-channels").json()["data"]["items"]
        assert len(items) == 1
        secret = items[0]["api_secret"]
        assert secret != SECRET
        assert secret == f"{SECRET[:3]}****{SECRET[-4:]}"

    def test_create_response_masks_api_secret(self, client):
        """POST create 响应同样掩码。"""
        r = client.post("/api/v1/system-config/payment-channels", json={
            "name": "支付宝", "channel_type": "alipay", "api_secret": SECRET,
        })
        assert r.status_code == 201
        secret = r.json()["data"]["api_secret"]
        assert secret != SECRET
        assert secret == f"{SECRET[:3]}****{SECRET[-4:]}"

    def test_short_secret_fully_masked(self, client):
        """短 secret (≤8) 全打码为 ****。"""
        client.post("/api/v1/system-config/payment-channels", json={
            "name": "银联", "channel_type": "unionpay", "api_secret": "short",
        })
        items = client.get("/api/v1/system-config/payment-channels").json()["data"]["items"]
        assert items[0]["api_secret"] == "****"


class TestListPermissionGate:
    def test_viewer_get_list_403(self, client, viewer_token):
        """非 admin 且无 system:config 权限 → GET 403。"""
        r = client.get("/api/v1/system-config/payment-channels",
                       headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 403

    def test_admin_get_list_200(self, client):
        """admin 仍可访问。"""
        assert client.get("/api/v1/system-config/payment-channels").status_code == 200


class TestUpdateMaskedSentinel:
    def test_put_masked_sentinel_keeps_real_secret(self, client):
        """PUT 回传掩码哨兵不覆盖已存明文 (GET 仍掩码)。"""
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "IM-B支付", "channel_type": "im_b", "api_secret": SECRET,
        }).json()["data"]["id"]

        masked = f"{SECRET[:3]}****{SECRET[-4:]}"
        r = client.put(f"/api/v1/system-config/payment-channels/{cid}", json={
            "name": "IM-B支付改", "api_secret": masked,
        })
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "IM-B支付改"

        # 掩码哨兵未写入: 拿底层库验证真实密钥仍在
        from app.api.v1.system_config.payment import _load_payment_channels
        channels = _load_payment_channels(client._sesh)
        assert channels[0]["api_secret"] == SECRET

        # GET 仍返回掩码
        items = client.get("/api/v1/system-config/payment-channels").json()["data"]["items"]
        assert items[0]["api_secret"] == masked

    def test_put_empty_secret_skipped(self, client):
        """PUT 空串同样跳过覆盖。"""
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "通道", "channel_type": "im_b", "api_secret": SECRET,
        }).json()["data"]["id"]
        client.put(f"/api/v1/system-config/payment-channels/{cid}", json={"api_secret": ""})
        from app.api.v1.system_config.payment import _load_payment_channels
        channels = _load_payment_channels(client._sesh)
        assert channels[0]["api_secret"] == SECRET

    def test_put_plaintext_updates_secret(self, client):
        """显式传明文可正常更新。"""
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "通道", "channel_type": "im_b", "api_secret": SECRET,
        }).json()["data"]["id"]
        new_secret = "brand-new-secret-xyz999"
        r = client.put(f"/api/v1/system-config/payment-channels/{cid}",
                       json={"api_secret": new_secret})
        assert r.status_code == 200
        assert r.json()["data"]["api_secret"] == f"{new_secret[:3]}****{new_secret[-4:]}"

        from app.api.v1.system_config.payment import _load_payment_channels
        channels = _load_payment_channels(client._sesh)
        assert channels[0]["api_secret"] == new_secret
