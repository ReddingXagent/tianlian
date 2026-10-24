"""卡 089b01b2 — 独立品牌端点 GET /tenants/{tenantId}/branding (契约§1).

端侧扫码/定位后先拿品牌再登录 → 匿名公开 (无 C端 token)。
复用 tenant_brand_service.branding_for_tenant; 租户未配置 → 天链默认品牌 (source=default)。
"""
import uuid

from app.models.tenant import Tenant
from app.models.tenant_brand import TenantBrand

BASE = "/api/v1/tenants"


def _seed_tenant_with_brand(session, *, operator_name="某某新能源",
                             theme_color="#FF0000",
                             logo_url="https://cdn.example/logo.png",
                             service_phone="400-888-0001"):
    t = Tenant(name=f"租户_{uuid.uuid4().hex[:6]}",
               code=f"T{uuid.uuid4().hex[:8].upper()}")
    session.add(t)
    session.commit()
    session.refresh(t)
    b = TenantBrand(
        tenant_id=t.id,
        operator_name=operator_name,
        theme_color=theme_color,
        logo_url=logo_url,
        service_phone=service_phone,
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return t, b


def test_branding_anonymous_default(client):
    """未配置品牌的 tenant → 天链默认品牌 (source=default), 匿名可访问。"""
    r = client.get(f"{BASE}/999999/branding")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["source"] == "default"
    assert data["operator_name"]  # 非空
    assert "theme_color" in data
    assert "logo_url" in data
    assert "service_phone" in data


def test_branding_tenant_configured(client):
    """已配置品牌 → source=tenant + 品牌字段, 匿名可访问。"""
    t, b = _seed_tenant_with_brand(client._sesh)
    r = client.get(f"{BASE}/{t.id}/branding")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["source"] == "tenant"
    assert data["operator_name"] == "某某新能源"
    assert data["theme_color"] == "#FF0000"
    assert data["logo_url"] == "https://cdn.example/logo.png"
    assert data["service_phone"] == "400-888-0001"


def test_branding_no_token_needed(anon_client, client):
    """匿名 (无任何 token) 可访问品牌端点 (端侧先拿品牌再登录)。"""
    t, _ = _seed_tenant_with_brand(client._sesh)
    r = anon_client.get(f"{BASE}/{t.id}/branding")
    assert r.status_code == 200
    assert r.json()["data"]["source"] == "tenant"
