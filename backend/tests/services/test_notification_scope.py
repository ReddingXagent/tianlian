"""NOTIFY_EVENT_SCOPE_MATRIX 通知事件作用域矩阵测试 (卡 8d98ebe3)

被测模块: app/services/notification_scope.py
account_type × event_domain 矩阵 + filter_events_for_account。
按账户类型过滤该用户应感知的事件域, 杜绝司机收设备故障、平台管理员收充电计费之类错配。
"""
from types import SimpleNamespace

from app.services.notification_scope import (
    ACCOUNT_EVENT_SCOPE_MATRIX,
    filter_events_for_account,
    ALLOWED_ACCOUNT_TYPES,
    ALLOWED_EVENT_DOMAINS,
)


def _ev(domain):
    return {"event_domain": domain, "name": f"evt-{domain}"}


ALL_EVENTS = [_ev(d) for d in [
    "system_security", "site_operation", "equipment_fault", "charging_billing"
]]


# ========== 矩阵定义 ==========

def test_matrix_covers_all_account_types():
    for at in ["platform_admin", "platform_operator", "fleet_operator",
               "engineer", "driver"]:
        assert at in ACCOUNT_EVENT_SCOPE_MATRIX


def test_matrix_values_are_valid_domains():
    for at, domains in ACCOUNT_EVENT_SCOPE_MATRIX.items():
        assert isinstance(domains, list)
        for d in domains:
            assert d in ALLOWED_EVENT_DOMAINS


def test_platform_admin_only_system_security():
    # 例 (卡面): platform_admin 只收 system_security
    assert ACCOUNT_EVENT_SCOPE_MATRIX["platform_admin"] == ["system_security"]


def test_fleet_operator_receives_charging_billing():
    # 例 (卡面): fleet_operator 收 charging_billing
    assert "charging_billing" in ACCOUNT_EVENT_SCOPE_MATRIX["fleet_operator"]


def test_engineer_receives_equipment_fault():
    assert "equipment_fault" in ACCOUNT_EVENT_SCOPE_MATRIX["engineer"]


# ========== filter_events_for_account ==========

def test_filter_platform_admin_keeps_only_security():
    out = filter_events_for_account(ALL_EVENTS, "platform_admin")
    assert [e["event_domain"] for e in out] == ["system_security"]


def test_filter_fleet_operator():
    out = filter_events_for_account(ALL_EVENTS, "fleet_operator")
    domains = {e["event_domain"] for e in out}
    assert "charging_billing" in domains
    assert "equipment_fault" not in domains
    assert "system_security" not in domains


def test_filter_platform_operator_gets_broad():
    out = filter_events_for_account(ALL_EVENTS, "platform_operator")
    domains = {e["event_domain"] for e in out}
    # 运营方覆盖全域运营
    assert domains == {"system_security", "site_operation",
                       "equipment_fault", "charging_billing"}


def test_filter_engineer():
    out = filter_events_for_account(ALL_EVENTS, "engineer")
    domains = {e["event_domain"] for e in out}
    assert "equipment_fault" in domains
    assert "charging_billing" not in domains


def test_filter_driver_only_charging_billing():
    out = filter_events_for_account(ALL_EVENTS, "driver")
    assert [e["event_domain"] for e in out] == ["charging_billing"]


def test_filter_unknown_account_type_returns_empty():
    assert filter_events_for_account(ALL_EVENTS, "unknown_role") == []


def test_filter_none_account_type_returns_empty():
    assert filter_events_for_account(ALL_EVENTS, None) == []


def test_filter_preserves_order():
    events = [_ev("charging_billing"), _ev("site_operation"), _ev("charging_billing")]
    out = filter_events_for_account(events, "fleet_operator")
    # fleet_operator 收 charging_billing + site_operation, 顺序保持
    assert [e["event_domain"] for e in out] == ["charging_billing", "site_operation", "charging_billing"]


def test_filter_empty_events():
    assert filter_events_for_account([], "platform_admin") == []


def test_filter_supports_object_events():
    # 事件为对象 (有 .event_domain 属性) 也能过滤
    objs = [SimpleNamespace(event_domain="equipment_fault"),
            SimpleNamespace(event_domain="charging_billing")]
    out = filter_events_for_account(objs, "engineer")
    assert len(out) == 1
    assert out[0].event_domain == "equipment_fault"


def test_filter_event_with_unknown_domain_dropped():
    events = [{"event_domain": "new_domain_not_in_matrix"}]
    out = filter_events_for_account(events, "platform_operator")
    assert out == []
