#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
租户品牌解析服务测试 (卡 e57dd197)

契约: backend/docs/contracts/user-client-contract.md §1 (场站响应 + branding)

覆盖:
- default_branding(lightweight=True/False): 字段集合
- branding_for_tenant: 有配置→source=tenant / 无配置→source=default / tenant_id=None
- branding_map: 多租户批量 / 重复 tenant_id 去重 / None 降级
- _record_fields: 正确提取四字段
"""
import pytest

from app.services import tenant_brand_service as tbs
from app.models.tenant_brand import TenantBrand


# ---------- default_branding ----------

class TestDefaultBranding:
    def test_full_fields_set(self):
        """全量默认品牌含 operator_name/logo_url/service_phone/theme_color + source=default。"""
        b = tbs.default_branding(lightweight=False)
        assert set(b.keys()) == {
            "operator_name", "logo_url", "service_phone", "theme_color", "source"
        }
        assert b["source"] == "default"
        assert b["operator_name"] == "天链"
        assert b["theme_color"] == "#00A86B"

    def test_light_fields_set(self):
        """轻量默认品牌仅含 operator_name/theme_color + source, 不含 logo_url/service_phone。"""
        b = tbs.default_branding(lightweight=True)
        assert set(b.keys()) == {"operator_name", "theme_color", "source"}
        assert "logo_url" not in b
        assert "service_phone" not in b
        assert b["source"] == "default"

    def test_all_fields_non_null(self):
        """契约: 端侧无需判空, 所有返回字段非 null。"""
        b = tbs.default_branding()
        for k, v in b.items():
            assert v is not None, f"{k} 不应为 None"

    def test_default_is_branding_defaults_to_full(self):
        """lightweight 默认 False → 全量。"""
        b = tbs.default_branding()
        assert "logo_url" in b and "service_phone" in b


# ---------- _record_fields ----------

class TestRecordFields:
    def test_extracts_four_fields(self):
        """_record_fields 从 TenantBrand 提取四字段。"""
        rec = TenantBrand(
            operator_name="某某新能源",
            logo_url="https://cdn.example/logo.png",
            service_phone="400-888-0001",
            theme_color="#AABBCC",
        )
        fields = tbs._record_fields(rec)
        assert fields == {
            "operator_name": "某某新能源",
            "logo_url": "https://cdn.example/logo.png",
            "service_phone": "400-888-0001",
            "theme_color": "#AABBCC",
        }

    def test_record_fields_keys_match_full_fields(self):
        """提取的 key 集合 == _FULL_FIELDS。"""
        rec = TenantBrand(
            operator_name="x", logo_url="y", service_phone="z", theme_color="w"
        )
        assert set(tbs._record_fields(rec).keys()) == set(tbs._FULL_FIELDS)


# ---------- branding_for_tenant ----------

class TestBrandingForTenant:
    def test_configured_tenant_source_tenant(self, test_db):
        """已配置品牌 → source=tenant, 取租户字段。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=101, operator_name="绿能科技",
            logo_url="https://cdn.example/101.png",
            service_phone="400-100-1010", theme_color="#112233",
        ))
        db.commit()

        b = tbs.branding_for_tenant(db, 101)
        assert b["source"] == "tenant"
        assert b["operator_name"] == "绿能科技"
        assert b["logo_url"] == "https://cdn.example/101.png"
        assert b["service_phone"] == "400-100-1010"
        assert b["theme_color"] == "#112233"
        db.close()

    def test_unconfigured_tenant_falls_back_default(self, test_db):
        """租户未配置品牌 → source=default, 用天链默认品牌。"""
        db = test_db["SessionLocal"]()
        b = tbs.branding_for_tenant(db, 999)  # 不存在的 tenant_id
        assert b["source"] == "default"
        assert b["operator_name"] == "天链"
        assert b["theme_color"] == "#00A86B"
        db.close()

    def test_tenant_id_none_falls_back_default(self, test_db):
        """tenant_id=None → 直接降级 default, 不查库。"""
        db = test_db["SessionLocal"]()
        b = tbs.branding_for_tenant(db, None)
        assert b["source"] == "default"
        assert b["operator_name"] == "天链"
        db.close()

    def test_lightweight_strips_logo_and_phone(self, test_db):
        """lightweight=True 即使有租户配置, 也只返回 operator_name/theme_color。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=102, operator_name="轻量租户",
            logo_url="https://cdn.example/102.png",
            service_phone="400-200-1020", theme_color="#445566",
        ))
        db.commit()

        b = tbs.branding_for_tenant(db, 102, lightweight=True)
        assert b["source"] == "tenant"
        assert set(b.keys()) == {"operator_name", "theme_color", "source"}
        assert b["operator_name"] == "轻量租户"
        db.close()

    def test_only_matching_tenant_resolved(self, test_db):
        """命中需精确匹配 tenant_id, 其他租户配置不串扰。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=200, operator_name="租户A",
            logo_url="", service_phone="", theme_color="#AAAAAA",
        ))
        db.commit()
        # 查 201 (未配置) 应降级, 不误取 200
        b = tbs.branding_for_tenant(db, 201)
        assert b["source"] == "default"
        assert b["operator_name"] == "天链"
        db.close()


# ---------- branding_map ----------

class TestBrandingMap:
    def test_batch_multiple_tenants(self, test_db):
        """多租户批量解析: 配置的取 tenant, 未配置的降级 default。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=10, operator_name="甲运营商",
            logo_url="u10", service_phone="p10", theme_color="#10",
        ))
        db.add(TenantBrand(
            tenant_id=20, operator_name="乙运营商",
            logo_url="u20", service_phone="p20", theme_color="#20",
        ))
        db.commit()

        m = tbs.branding_map(db, [10, 20, 30])  # 30 未配置
        assert set(m.keys()) == {10, 20, 30}
        assert m[10]["source"] == "tenant"
        assert m[10]["operator_name"] == "甲运营商"
        assert m[20]["operator_name"] == "乙运营商"
        assert m[30]["source"] == "default"
        db.close()

    def test_dedup_repeated_tenant_ids(self, test_db):
        """重复 tenant_id 去重: 返回 dict 每键仅一份。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=40, operator_name="重复租户",
            logo_url="", service_phone="", theme_color="#40",
        ))
        db.commit()

        m = tbs.branding_map(db, [40, 40, 40])
        assert list(m.keys()) == [40]  # 去重后单键
        assert m[40]["source"] == "tenant"
        assert m[40]["operator_name"] == "重复租户"
        db.close()

    def test_none_key_degrades_default(self, test_db):
        """None 作为 tenant_id 参与去重并降级为 default。"""
        db = test_db["SessionLocal"]()
        m = tbs.branding_map(db, [None, None, 50])  # 50 未配置
        assert set(m.keys()) == {None, 50}
        assert m[None]["source"] == "default"
        assert m[50]["source"] == "default"
        db.close()

    def test_mixed_with_configured_and_none_and_dup(self, test_db):
        """混合: 配置租户 + None + 重复键, 去重且各自正确解析。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=60, operator_name="混合租户",
            logo_url="u60", service_phone="p60", theme_color="#60",
        ))
        db.commit()

        m = tbs.branding_map(db, [60, None, 60, None, 70])
        assert set(m.keys()) == {60, None, 70}
        assert m[60]["source"] == "tenant"
        assert m[None]["source"] == "default"
        assert m[70]["source"] == "default"
        db.close()

    def test_empty_input(self, test_db):
        """空输入 → 空映射。"""
        db = test_db["SessionLocal"]()
        assert tbs.branding_map(db, []) == {}
        db.close()

    def test_lightweight_batch(self, test_db):
        """批量轻量: 每项仅 operator_name/theme_color。"""
        db = test_db["SessionLocal"]()
        db.add(TenantBrand(
            tenant_id=80, operator_name="轻批租户",
            logo_url="u80", service_phone="p80", theme_color="#80",
        ))
        db.commit()

        m = tbs.branding_map(db, [80], lightweight=True)
        assert set(m[80].keys()) == {"operator_name", "theme_color", "source"}
        assert m[80]["source"] == "tenant"
        db.close()
