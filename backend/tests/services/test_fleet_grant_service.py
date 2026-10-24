#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
车队设备授权 scope 服务测试 (卡 e57dd197)

契约: app/services/fleet_grant_service.py (与 EnterpriseDeviceGrant 表配合)

授权语义:
- 企业无授权记录 → 放行(向后兼容)
- 整站授权(device_id IS NULL 且 station_id 匹配) → 该站所有桩放行
- 桩级授权(device_id 匹配) → 仅该桩
- 否则 → 拒绝
"""
import pytest

from app.services.fleet_grant_service import is_device_authorized
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.enterprise_device_grant import EnterpriseDeviceGrant


def _make_device(station_id, dev_id=None):
    """构造一个 Device 实例 (不落库, 仅取 id/station_id 属性)。"""
    d = Device(
        sn=f"SN-GRANT-{station_id}-{dev_id}",
        name=f"桩-{dev_id}",
        code=f"DEV{dev_id}",
        type=DeviceType.CHARGER_DC,
        status=DeviceStatus.ONLINE,
        station_id=station_id,
    )
    if dev_id is not None:
        d.id = dev_id
    return d


class TestIsDeviceAuthorized:
    def test_no_grants_pass_through(self, test_db):
        """企业无任何授权记录 → 放行 (向后兼容, baseline)。"""
        db = test_db["SessionLocal"]()
        device = _make_device(station_id=5, dev_id=100)
        allowed, reason = is_device_authorized(db, enterprise_id=1, device=device)
        assert allowed is True
        assert "放行" in reason
        db.close()

    def test_station_level_grant_matches_station(self, test_db):
        """整站授权(device_id=None, station_id 匹配) → 该站所有桩放行。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=2, station_id=7, device_id=None,  # 整站授权
        ))
        db.commit()

        device = _make_device(station_id=7, dev_id=200)  # 站内任一桩
        allowed, reason = is_device_authorized(db, enterprise_id=2, device=device)
        assert allowed is True
        assert "整站授权" in reason
        db.close()

    def test_device_level_grant_matches_device(self, test_db):
        """桩级授权(device_id 匹配) → 仅该桩放行。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=3, station_id=9, device_id=300,  # 桩级授权
        ))
        db.commit()

        device = _make_device(station_id=9, dev_id=300)
        allowed, reason = is_device_authorized(db, enterprise_id=3, device=device)
        assert allowed is True
        assert "桩级授权" in reason
        db.close()

    def test_grant_exists_but_device_out_of_scope(self, test_db):
        """有授权但设备不在范围(别的桩) → 拒绝。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=4, station_id=11, device_id=400,  # 只授权桩 400
        ))
        db.commit()

        device = _make_device(station_id=11, dev_id=499)  # 同站但另一桩
        allowed, reason = is_device_authorized(db, enterprise_id=4, device=device)
        assert allowed is False
        assert "不在" in reason or "授权范围" in reason
        db.close()

    def test_station_grant_misses_different_station(self, test_db):
        """整站授权, 但设备属不同 station_id → 不命中 → 拒绝。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=5, station_id=13, device_id=None,  # 整站授权 站13
        ))
        db.commit()

        device = _make_device(station_id=99, dev_id=500)  # 设备在站99
        allowed, reason = is_device_authorized(db, enterprise_id=5, device=device)
        assert allowed is False
        assert "不在" in reason or "授权范围" in reason
        db.close()

    def test_device_grant_misses_different_device(self, test_db):
        """桩级授权, device_id 不匹配 → 拒绝 (即使 station 也不一致)。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=6, station_id=15, device_id=600,
        ))
        db.commit()

        device = _make_device(station_id=15, dev_id=699)  # 同站, 桩不匹配
        allowed, reason = is_device_authorized(db, enterprise_id=6, device=device)
        assert allowed is False
        db.close()

    def test_mixed_station_and_device_grants(self, test_db):
        """同企业同时存在整站+桩级授权: 站内任意桩命中整站规则。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=7, station_id=17, device_id=None,   # 整站
        ))
        db.add(EnterpriseDeviceGrant(
            enterprise_id=7, station_id=18, device_id=800,    # 桩级
        ))
        db.commit()

        # 站17 任一桩 → 整站命中
        dev_in_station17 = _make_device(station_id=17, dev_id=701)
        allowed, reason = is_device_authorized(db, 7, dev_in_station17)
        assert allowed is True
        assert "整站授权" in reason

        # 站18 桩 800 → 桩级命中
        dev_granted = _make_device(station_id=18, dev_id=800)
        allowed, reason = is_device_authorized(db, 7, dev_granted)
        assert allowed is True
        assert "桩级授权" in reason

        # 站18 其他桩 → 均不命中 → 拒绝
        dev_other = _make_device(station_id=18, dev_id=899)
        allowed, reason = is_device_authorized(db, 7, dev_other)
        assert allowed is False
        db.close()

    def test_other_enterprise_grants_do_not_apply(self, test_db):
        """企业的授权互不干扰: A 企业授权不覆盖 B 企业设备校验。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=8, station_id=20, device_id=900,  # 企业8 授权桩900
        ))
        db.commit()

        # 企业9 无任何授权 → 放行 (即使桩900 被企业8 独占)
        device = _make_device(station_id=20, dev_id=900)
        allowed, reason = is_device_authorized(db, enterprise_id=9, device=device)
        assert allowed is True
        assert "放行" in reason
        db.close()

    def test_reason_message_includes_ids(self, test_db):
        """拒绝 reason 应含 device.id 与 station_id 上下文, 便于排障。"""
        db = test_db["SessionLocal"]()
        db.add(EnterpriseDeviceGrant(
            enterprise_id=10, station_id=25, device_id=1000,
        ))
        db.commit()

        device = _make_device(station_id=25, dev_id=1001)
        allowed, reason = is_device_authorized(db, enterprise_id=10, device=device)
        assert allowed is False
        assert "1001" in reason  # device.id
        assert "25" in reason    # station_id
        db.close()
