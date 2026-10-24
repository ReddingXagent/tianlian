#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常保护加固测试 (卡 12cc84a9)

验证 tenant_brand_service / fleet_grant_service 在 DB 查询抛异常时,
走 logger.exception() 并降级返回 (不向调用方 raise)。

加固策略:
- branding_for_tenant: 异常 → 默认品牌 (source=default)
- branding_map:        异常 → 每个 tenant_id 降级默认品牌 (含 None 键, 保持映射一一对应)
- is_device_authorized: 异常 → (True, '...降级放行') (向后兼容, 保 baseline)

DB 异常用 MagicMock 触发, 不依赖真实 Session 状态。
"""
from unittest.mock import MagicMock

import pytest

from app.services import tenant_brand_service as tbs
from app.services import fleet_grant_service as fgs


def _mock_db_query_raises(exc: Exception) -> MagicMock:
    """构造一个 Session: 任意 db.query(...).filter(...).first()/all() 都抛 exc。

    query() 返回的对象支持链式 .filter()/.all()/first() —— 全部抛异常。
    """
    db = MagicMock()
    # query() 本身不抛, 链尾 .first()/.all() 抛, 以模拟查询执行失败
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.first.side_effect = exc
    chain.all.side_effect = exc
    db.query.return_value = chain
    return db


# ---------- tenant_brand_service ----------

class TestBrandingForTenantHardening:
    def test_db_exception_falls_back_to_default(self):
        """branding_for_tenant: DB 查询抛异常 → 不 raise, 降级默认品牌。"""
        db = _mock_db_query_raises(RuntimeError("db connection lost"))

        b = tbs.branding_for_tenant(db, tenant_id=123)

        assert b["source"] == "default"
        assert b["operator_name"] == "天链"
        assert b["theme_color"] == "#00A86B"
        # 全量默认字段齐备
        assert set(b.keys()) == {
            "operator_name", "logo_url", "service_phone", "theme_color", "source"
        }


class TestBrandingMapHardening:
    def test_db_exception_degrades_every_key(self):
        """branding_map: DB 查询抛异常 → 每个 tenant_id(含 None) 降级默认品牌, 保持一一对应。"""
        db = _mock_db_query_raises(RuntimeError("db connection lost"))

        m = tbs.branding_map(db, [10, 20, None, 10])  # 含重复与 None

        # 键集合与去重后输入一致 (含 None)
        assert set(m.keys()) == {10, 20, None}
        for key in m:
            assert m[key]["source"] == "default"
            assert m[key]["operator_name"] == "天链"

    def test_db_exception_empty_input_returns_empty(self):
        """branding_map: 异常分支下空输入仍返回空映射 (不触发查询)。"""
        db = _mock_db_query_raises(RuntimeError("boom"))

        assert tbs.branding_map(db, []) == {}


# ---------- fleet_grant_service ----------

class TestIsDeviceAuthorizedHardening:
    def test_db_exception_degrades_to_allow(self):
        """is_device_authorized: DB 查询抛异常 → (True, 降级放行), 不 raise。"""
        db = _mock_db_query_raises(RuntimeError("db connection lost"))
        device = MagicMock()
        device.id = 555
        device.station_id = 7

        allowed, reason = fgs.is_device_authorized(db, enterprise_id=42, device=device)

        assert allowed is True
        assert "降级放行" in reason
