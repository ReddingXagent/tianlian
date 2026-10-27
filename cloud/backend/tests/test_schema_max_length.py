"""卡05d1383e: 请求schema str字段max_length与DB String(n)对齐。

生产PG超长输入应在Pydantic层422，而非DB溢出500。
"""

import pytest
from pydantic import ValidationError

from app.api.v1.alarm_rules import AlarmRuleCreate, AlarmRuleUpdate
from app.api.v1.fleet_drivers import DriverCreateRequest, DriverUpdateRequest
from app.api.v1.gateways import GatewayCreate, GatewayUpdate
from app.api.v1.inspection import (
    PlanCreate,
    PlanUpdate,
    TaskCreate,
    TaskUpdate,
    TemplateCreate,
    TemplateUpdate,
)
from app.api.v1.stations import StationCreate, StationUpdate


CASES = [
    (StationCreate, {"name": "n", "region": "HN"}, "name", 100),
    (StationUpdate, {"name": "n"}, "name", 100),
    (AlarmRuleCreate, {"name": "n", "metric": "m", "threshold": 1.0}, "name", 100),
    (AlarmRuleUpdate, {"name": "n"}, "name", 100),
    (GatewayCreate, {"sn": "SN1", "name": "n"}, "name", 100),
    (GatewayUpdate, {"name": "n"}, "name", 100),
    (PlanCreate, {"name": "n"}, "name", 200),
    (PlanUpdate, {"name": "n"}, "name", 200),
    (TaskCreate, {"name": "n"}, "name", 200),
    (TaskUpdate, {"name": "n"}, "name", 200),
    (TemplateCreate, {"name": "n"}, "name", 200),
    (TemplateUpdate, {"name": "n"}, "name", 200),
    (TaskCreate, {"name": "n", "station_name": "s"}, "station_name", 200),
    (DriverCreateRequest, {"enterprise_id": 1, "name": "n", "phone": "p", "license_no": "L"}, "name", 100),
    (DriverUpdateRequest, {"name": "n"}, "name", 100),
]


@pytest.mark.parametrize(("schema", "base", "field", "limit"), CASES)
def test_name_max_length(schema, base, field, limit):
    ok = schema(**{**base, field: "a" * limit})
    assert getattr(ok, field) == "a" * limit
    with pytest.raises(ValidationError):
        schema(**{**base, field: "a" * (limit + 1)})


def test_task_update_remark_max_length():
    TaskUpdate(remark="a" * 500)
    with pytest.raises(ValidationError):
        TaskUpdate(remark="a" * 501)
