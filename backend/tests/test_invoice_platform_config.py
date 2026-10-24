"""
运营-第三方开票平台配置 API 测试

覆盖 /api/v1/operate/invoice-platforms (invoice_platform_config.py):
- CRUD: 创建/列表/更新/删除
- 团队隔离: A团队看不到B团队配置
- 默认平台切换: 设为默认时自动清除旧默认
- 启用/禁用筛选
- 平台类型筛选
"""
import bcrypt
import ipaddress
import socket

import pytest

from app.core import url_safety
from app.models.ops_settlement.invoice_platform_config import (
    InvoicePlatformConfig, PlatformType,
)


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """SSRF 校验(卡 fb8b8106)需解析出站 URL 主机名; 测试环境无 DNS,
    域名一律伪造解析为公网 IP, 不触发真实网络。"""
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            return real_getaddrinfo(host, *args, **kwargs)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


# ─── 越权测试脚手架 ───

@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(operator, 具 operate:manage) + token，用于 team_id 越权测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="开票团队A", code="INVPNA")
    tb = Team(name="开票团队B", code="INVPNB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "inv123456"
    ua = User(
        username="inv_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="inv_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "tokens": {"a": _tok("inv_eng_a"), "b": _tok("inv_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_platform(session, team_id=1, **kw):
    """创建一条平台配置"""
    defaults = dict(
        team_id=team_id,
        platform_type=PlatformType.BAIWANG,
        platform_name="百旺测试",
        api_url="https://api.baiwang.com",
        app_key="ak001",
        app_secret="sk001",
        taxpayer_id="91110000MA00ABCD",
        tax_classification_code="1010101010000000000",
        is_default=False,
        enabled=True,
    )
    defaults.update(kw)
    p = InvoicePlatformConfig(**defaults)
    session.add(p)
    session.commit()
    return p


class TestInvoicePlatformCRUD:
    """开票平台 CRUD 基础测试"""

    def test_create_platform(self, client):
        """创建平台配置"""
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "team_id": 1,
            "platform_type": "baiwang",
            "platform_name": "百旺生产环境",
            "api_url": "https://api.baiwang.com/v1",
            "app_key": "bk001",
            "app_secret": "bs001",
            "taxpayer_id": "91110000MA00ABCD",
            "tax_classification_code": "1010101010000000000",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] > 0
        assert data["platform_type"] == "baiwang"
        assert data["platform_name"] == "百旺生产环境"
        assert data["is_default"] is False
        assert data["enabled"] is True

    def test_list_platforms(self, client):
        """列表查询"""
        _seed_platform(client._sesh, team_id=1, platform_name="百旺")
        _seed_platform(client._sesh, team_id=1, platform_type=PlatformType.NUONUO, platform_name="诺诺")
        _seed_platform(client._sesh, team_id=1, platform_type=PlatformType.HANGXIN, platform_name="航信")

        r = client.get("/api/v1/operate/invoice-platforms?team_id=1").json()["data"]
        assert r["total"] == 3
        names = {p["platform_name"] for p in r["items"]}
        assert names == {"百旺", "诺诺", "航信"}

    def test_list_with_platform_type_filter(self, client):
        """平台类型筛选"""
        _seed_platform(client._sesh, team_id=1, platform_type=PlatformType.BAIWANG, platform_name="A")
        _seed_platform(client._sesh, team_id=1, platform_type=PlatformType.NUONUO, platform_name="B")

        r = client.get("/api/v1/operate/invoice-platforms?team_id=1&platform_type=nuonuo").json()["data"]
        assert r["total"] == 1
        assert r["items"][0]["platform_name"] == "B"

    def test_list_with_enabled_filter(self, client):
        """启用状态筛选"""
        _seed_platform(client._sesh, team_id=1, platform_name="启用", enabled=True)
        _seed_platform(client._sesh, team_id=1, platform_name="禁用", enabled=False)

        r = client.get("/api/v1/operate/invoice-platforms?team_id=1&enabled=true").json()["data"]
        assert r["total"] == 1
        assert r["items"][0]["platform_name"] == "启用"

    def test_update_platform(self, client):
        """更新平台配置"""
        p = _seed_platform(client._sesh, team_id=1)

        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "platform_name": "百旺更新",
            "app_key": "new_key",
            "enabled": False,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["platform_name"] == "百旺更新"
        assert data["app_key"] == "new_key"
        assert data["enabled"] is False

    def test_delete_platform(self, client):
        """删除平台配置"""
        p = _seed_platform(client._sesh, team_id=1)

        r = client.delete(f"/api/v1/operate/invoice-platforms/{p.id}")
        assert r.status_code == 200

        # 确认已删除
        lst = client.get(f"/api/v1/operate/invoice-platforms?team_id=1").json()["data"]
        assert lst["total"] == 0

    def test_update_404(self, client):
        """更新不存在的平台 -> 404"""
        r = client.put("/api/v1/operate/invoice-platforms/99999", json={"platform_name": "x"})
        assert r.status_code == 404

    def test_delete_404(self, client):
        """删除不存在的平台 -> 404"""
        r = client.delete("/api/v1/operate/invoice-platforms/99999")
        assert r.status_code == 404

    def test_create_missing_team_id(self, client):
        """body 缺 team_id 不再 422（任务卡 708350b3: team_id 服务端取）。"""
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "baiwang",
            "platform_name": "无团队",
        })
        assert r.status_code == 200
        # admin → team_id=0；客户端 team_id 一律忽略
        assert r.json()["data"]["team_id"] == 0

    def test_create_ignores_client_team_id(self, client):
        """body 伪造 team_id=999 被忽略，按服务端身份归属（admin→0）。"""
        r = client.post("/api/v1/operate/invoice-platforms", json={
            "platform_type": "baiwang",
            "platform_name": "伪造团队",
            "team_id": 999,
        })
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == 0


class TestTeamIsolation:
    """团队隔离测试: A团队看不到B团队配置"""

    def test_team_isolation_list(self, client, team_pair):
        """团队级用户只看本 team 配置；伪造 query team_id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        _seed_platform(client._sesh, team_id=ta.id, platform_name="团队A-百旺")
        _seed_platform(client._sesh, team_id=tb.id, platform_name="团队B-航信",
                       platform_type=PlatformType.HANGXIN)

        # A 用户故意伪造 ?team_id=B，仍只看到本 team
        r_a = client.get(
            f"/api/v1/operate/invoice-platforms?team_id={tb.id}",
            headers=_h(team_pair["tokens"]["a"]),
        ).json()["data"]
        assert r_a["total"] == 1
        assert r_a["items"][0]["platform_name"] == "团队A-百旺"

        # B 用户只看到本 team
        r_b = client.get(
            "/api/v1/operate/invoice-platforms",
            headers=_h(team_pair["tokens"]["b"]),
        ).json()["data"]
        assert r_b["total"] == 1
        assert r_b["items"][0]["platform_name"] == "团队B-航信"

    def test_cross_team_update_returns_404(self, client, team_pair):
        """团队级用户更新他队平台 → 404。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        p = _seed_platform(client._sesh, team_id=tb.id, platform_name="B的平台")
        r = client.put(
            f"/api/v1/operate/invoice-platforms/{p.id}",
            json={"platform_name": "被篡改"},
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert r.status_code == 404

    def test_cross_team_update_not_isolated_on_write(self, client):
        """确认 team_id 不在更新中（不可通过 API 改 team_id）"""
        p = _seed_platform(client._sesh, team_id=1)
        client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "platform_name": "跨团队改",
        })
        # team_id 不可改（不在可更新字段列表）
        s = client._sesh
        refreshed = s.query(InvoicePlatformConfig).filter_by(id=p.id).first()
        assert refreshed.team_id == 1


class TestDefaultPlatformSwitch:
    """默认平台切换测试"""

    def test_set_default_clears_old(self, client):
        """设新默认时自动清除旧默认"""
        p1 = _seed_platform(client._sesh, team_id=1, platform_name="P1", is_default=True)
        p2 = _seed_platform(client._sesh, team_id=1, platform_name="P2", is_default=False)

        # 将 P2 设为默认
        r = client.put(f"/api/v1/operate/invoice-platforms/{p2.id}/default")
        assert r.status_code == 200
        assert r.json()["data"]["is_default"] is True

        # 确认 P1 已取消默认
        s = client._sesh
        s.refresh(p1)
        assert p1.is_default is False

    def test_create_with_default_clears_old(self, client):
        """创建时标记 is_default=True 自动清除旧默认"""
        # admin 创建归属 team_id=0；旧默认也需 seed 在 team_id=0 才会被清除
        p1 = _seed_platform(client._sesh, team_id=0, platform_name="P1", is_default=True)

        r = client.post("/api/v1/operate/invoice-platforms", json={
            "team_id": 1,
            "platform_type": "nuonuo",
            "platform_name": "P2",
            "is_default": True,
        })
        assert r.status_code == 200

        # P1 应已取消默认
        s = client._sesh
        s.refresh(p1)
        assert p1.is_default is False

    def test_default_ordering(self, client):
        """默认平台在列表中排在前面"""
        _seed_platform(client._sesh, team_id=1, platform_name="A", is_default=False)
        _seed_platform(client._sesh, team_id=1, platform_name="B", is_default=True)
        _seed_platform(client._sesh, team_id=1, platform_name="C", is_default=False)

        r = client.get("/api/v1/operate/invoice-platforms?team_id=1").json()["data"]
        assert r["items"][0]["platform_name"] == "B"  # 默认排第一
        assert r["items"][0]["is_default"] is True

    def test_default_not_cross_team(self, client):
        """设默认不影响其他团队"""
        p_a = _seed_platform(client._sesh, team_id=1, platform_name="A", is_default=True)
        p_b = _seed_platform(client._sesh, team_id=2, platform_name="B", is_default=True)

        # 给 team 1 新增一个默认
        p_a2 = _seed_platform(client._sesh, team_id=1, platform_name="A2", is_default=False)
        client.put(f"/api/v1/operate/invoice-platforms/{p_a2.id}/default")

        # team 2 的默认不受影响
        s = client._sesh
        s.refresh(p_b)
        assert p_b.is_default is True

    def test_set_default_404(self, client):
        """设默认: 不存在 -> 404"""
        r = client.put("/api/v1/operate/invoice-platforms/99999/default")
        assert r.status_code == 404


# ======================================================================
# 异常路径加固 (卡 416f2bb4)
# ======================================================================

def test_create_platform_integrity_conflict(client, monkeypatch):
    """创建平台配置遇唯一约束冲突 → 409, 不冒泡 500。"""
    from sqlalchemy.exc import IntegrityError

    def _boom(*a, **kw):
        raise IntegrityError("simulated", {}, Exception("UNIQUE"))

    monkeypatch.setattr(client._sesh, "commit", _boom)

    r = client.post("/api/v1/operate/invoice-platforms", json={
        "platform_type": "baiwang",
        "platform_name": "冲突平台",
        "taxpayer_id": "91110000MA00ABCD",
    })
    assert r.status_code == 409


# ======================================================================
# 掩码哨兵防回写 (卡 7ada32c8)
# ======================================================================

class TestMaskedSecretSentinel:
    """GET 回填掩码 app_secret / private_key_enc 再 PUT 时，不得覆盖真实值。"""

    def test_update_masked_app_secret_preserved(self, client):
        """掩码 app_secret (****尾4) 回传 → DB 保留真实值。"""
        p = _seed_platform(client._sesh, team_id=1, app_secret="real-secret-abc123")
        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "platform_name": "改名",
            "app_secret": "****c123",  # _mask_secret 产物形态
        })
        assert r.status_code == 200
        s = client._sesh
        s.refresh(p)
        assert p.app_secret == "real-secret-abc123"
        assert p.platform_name == "改名"

    def test_update_real_app_secret_takes_effect(self, client):
        """真实新 app_secret → 正常生效。"""
        p = _seed_platform(client._sesh, team_id=1, app_secret="old-secret")
        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "app_secret": "brand-new-secret",
        })
        assert r.status_code == 200
        s = client._sesh
        s.refresh(p)
        assert p.app_secret == "brand-new-secret"

    def test_update_masked_private_key_preserved(self, client):
        """掩码 private_key_enc 回传 → 跳过 setattr/encrypt, 保留 DB 密文。"""
        from app.core.crypto_utils import encrypt_field
        p = _seed_platform(client._sesh, team_id=1,
                           private_key_enc=encrypt_field("-----BEGIN RSA PRIVATE KEY-----test"))
        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "platform_name": "改名",
            "private_key_enc": "****abcd",  # _mask_secret 产物形态
        })
        assert r.status_code == 200
        s = client._sesh
        s.refresh(p)
        assert p.private_key_enc != "****abcd"
        assert p.private_key_enc.startswith("gAAAA") or "BEGIN" not in p.private_key_enc
        # 解密后仍是原私钥明文
        from app.core.crypto_utils import decrypt_field
        assert decrypt_field(p.private_key_enc) == "-----BEGIN RSA PRIVATE KEY-----test"

    def test_update_empty_private_key_clears(self, client):
        """传空串仍清空为 None（既有语义不变）。"""
        from app.core.crypto_utils import encrypt_field
        p = _seed_platform(client._sesh, team_id=1,
                           private_key_enc=encrypt_field("secret-pem"))
        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "private_key_enc": "",
        })
        assert r.status_code == 200
        s = client._sesh
        s.refresh(p)
        assert p.private_key_enc is None

    def test_update_real_private_key_updates(self, client):
        """真实新私钥明文 → 加密落库。"""
        p = _seed_platform(client._sesh, team_id=1)
        r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
            "private_key_enc": "-----BEGIN RSA PRIVATE KEY-----new",
        })
        assert r.status_code == 200
        s = client._sesh
        s.refresh(p)
        from app.core.crypto_utils import decrypt_field
        assert decrypt_field(p.private_key_enc) == "-----BEGIN RSA PRIVATE KEY-----new"


def test_update_platform_db_error(client, monkeypatch):
    """更新遇非约束类 DB 异常 → 500, 不泄露原始异常。"""
    p = _seed_platform(client._sesh, team_id=1)

    def _boom(*a, **kw):
        raise RuntimeError("DB 连接断开")

    monkeypatch.setattr(client._sesh, "commit", _boom)

    r = client.put(f"/api/v1/operate/invoice-platforms/{p.id}", json={
        "platform_name": "改名",
    })
    assert r.status_code == 500
    assert "DB 连接断开" not in str(r.json().get("detail", ""))
