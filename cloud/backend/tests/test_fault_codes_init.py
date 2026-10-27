"""故障码初始化单测 — 卡 d349df9d"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.data.fault_codes_init import (
    ALL_FAULT_CODES,
    CHARGER_FAULT_CODES,
    INVERTER_FAULT_CODES,
    PCS_FAULT_CODES,
    init_fault_codes,
)
from app.models.fault_code import FaultCode


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FaultCode.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_constants_and_concat():
    assert len(INVERTER_FAULT_CODES) > 0
    assert len(CHARGER_FAULT_CODES) > 0
    assert len(PCS_FAULT_CODES) > 0
    assert ALL_FAULT_CODES == INVERTER_FAULT_CODES + CHARGER_FAULT_CODES + PCS_FAULT_CODES


def test_init_fault_codes_no_exception_and_inserted(db):
    """不抛 NameError（历史缺陷：缺 import logging），数据入库"""
    init_fault_codes(db)  # 若缺 import logging 此处抛 NameError
    assert db.query(FaultCode).count() == len(ALL_FAULT_CODES)


def test_init_fault_codes_idempotent(db):
    init_fault_codes(db)
    init_fault_codes(db)
    assert db.query(FaultCode).count() == len(ALL_FAULT_CODES)
