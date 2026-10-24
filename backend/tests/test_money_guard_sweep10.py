"""资金守卫第10弹收官——maintenance/stations/vpp 资金与容量字段 ge=0 守卫 (卡3c6a57b5)"""

import pytest
from pydantic import ValidationError

from app.api.v1.maintenance_records import MaintenanceRecordCreate, MaintenanceRecordUpdate
from app.api.v1.stations import StationUpdate
from app.api.v1.vpp import StationRegisterRequest, GridSignalRequest


def _make(cls, **overrides):
    """填必填字段后覆盖 overrides"""
    base = {}
    if cls is MaintenanceRecordCreate:
        base = {"device_id": 1, "title": "t"}
    elif cls is StationRegisterRequest:
        base = {"station_id": "st-1", "station_name": "s"}
    elif cls is GridSignalRequest:
        base = {"signal_type": "peak", "start_time": "2026-01-01T00:00:00", "end_time": "2026-01-01T01:00:00"}
    elif cls is StationUpdate:
        base = {}
    base.update(overrides)
    return cls(**base)


# ---------- maintenance_records cost ----------
@pytest.mark.parametrize("model", [MaintenanceRecordCreate, MaintenanceRecordUpdate])
def test_maintenance_cost_negative_rejected(model):
    with pytest.raises(ValidationError):
        _make(model, cost=-1)


@pytest.mark.parametrize("model", [MaintenanceRecordCreate, MaintenanceRecordUpdate])
@pytest.mark.parametrize("cost", [0, 100])
def test_maintenance_cost_nonnegative_ok(model, cost):
    assert _make(model, cost=cost).cost == cost


# ---------- stations total_cost ----------
def test_station_total_cost_negative_rejected():
    with pytest.raises(ValidationError):
        _make(StationUpdate, total_cost=-0.01)


@pytest.mark.parametrize("cost", [0, 1234.5])
def test_station_total_cost_nonnegative_ok(cost):
    assert _make(StationUpdate, total_cost=cost).total_cost == cost


# ---------- vpp StationRegisterRequest 容量字段 ----------
@pytest.mark.parametrize("field", ["total_pv_kw", "total_battery_kwh", "total_ev_chargers"])
def test_vpp_capacity_negative_rejected(field):
    with pytest.raises(ValidationError):
        _make(StationRegisterRequest, **{field: -1})


@pytest.mark.parametrize("field", ["total_pv_kw", "total_battery_kwh", "total_ev_chargers"])
def test_vpp_capacity_nonnegative_ok(field):
    assert getattr(_make(StationRegisterRequest, **{field: 0}), field) == 0
    assert getattr(_make(StationRegisterRequest, **{field: 10}), field) == 10


# ---------- vpp GridSignalRequest 价格字段 (Optional: None 放行) ----------
@pytest.mark.parametrize("field", ["price_per_kwh", "reward_per_kwh", "penalty_per_kwh"])
def test_grid_signal_negative_rejected(field):
    with pytest.raises(ValidationError):
        _make(GridSignalRequest, **{field: -0.01})


@pytest.mark.parametrize("field", ["price_per_kwh", "reward_per_kwh", "penalty_per_kwh"])
def test_grid_signal_none_and_nonnegative_ok(field):
    assert getattr(_make(GridSignalRequest, **{field: None}), field) is None
    assert getattr(_make(GridSignalRequest, **{field: 0}), field) == 0
    assert getattr(_make(GridSignalRequest, **{field: 1.5}), field) == 1.5
