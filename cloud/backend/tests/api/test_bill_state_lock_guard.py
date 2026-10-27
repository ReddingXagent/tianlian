#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fleet 结算账单状态机锁加固回归测试 (卡 63a3fa8a)。

覆盖 2 个端点:
- POST /api/v1/fleet/bills/{id}/confirm  confirm_bill (pending → confirmed)
- POST /api/v1/fleet/bills/{id}/pay      pay_bill     (confirmed → paid)

修复内容: 状态机流转前以 with_for_update().populate_existing() 行锁读账单,
消除并发 confirm/pay 之间读-判-写 TOCTOU 覆写窗口。生产 PostgreSQL 下真正锁行;
SQLite 测试环境下 with_for_update 为 no-op, 本套件验证行为契约不变:

(a) confirm PENDING → 200 且状态 confirmed
(b) 重复 confirm (已 confirmed) → 400
(c) pay 未确认 (pending) → 400
(d) pay 超过 total_amount → 400
(e) pay 成功 → 200 且 paid / balance_amount = total - paid
(f) 账单不存在 → 404
"""
from decimal import Decimal

import pytest

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.settlement.bill import BillStatus, FleetSettlementBill

CONFIRM_URL = "/api/v1/fleet/settlement/bills/{bid}/confirm"
PAY_URL = "/api/v1/fleet/settlement/bills/{bid}/pay"


@pytest.fixture
def enterprise(db_session):
    ent = Enterprise(
        name="账单状态锁测试企业", code="BILL-LOCK-ENT",
        status=EnterpriseStatus.ACTIVE,
        balance=Decimal("100.00"), credit_limit=Decimal("0.00"),
    )
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent


def _make_bill(db_session, enterprise, status=BillStatus.PENDING,
               total=Decimal("100.00")):
    bill = FleetSettlementBill(
        bill_no="BL-LOCK-001",
        enterprise_id=enterprise.id,
        bill_period="2026-08",
        total_amount=total,
        status=status,
    )
    db_session.add(bill)
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestConfirmBillStateLock:
    def test_confirm_pending_success(self, client, enterprise, db_session):
        bill = _make_bill(db_session, enterprise)
        res = client.post(CONFIRM_URL.format(bid=bill.id))
        assert res.status_code == 200, res.text
        body = res.json()["data"]
        assert body["status"] == "confirmed"

    def test_confirm_twice_400(self, client, enterprise, db_session):
        bill = _make_bill(db_session, enterprise, status=BillStatus.CONFIRMED)
        res = client.post(CONFIRM_URL.format(bid=bill.id))
        assert res.status_code == 400
        assert "无法确认" in res.json()["detail"]

    def test_confirm_not_found_404(self, client):
        res = client.post(CONFIRM_URL.format(bid=99999999))
        assert res.status_code == 404
        assert res.json()["detail"] == "账单不存在"


class TestPayBillStateLock:
    def test_pay_not_confirmed_400(self, client, enterprise, db_session):
        bill = _make_bill(db_session, enterprise, status=BillStatus.PENDING)
        res = client.post(PAY_URL.format(bid=bill.id), json={"paid_amount": "10.00"})
        assert res.status_code == 400
        assert "需先确认" in res.json()["detail"]

    def test_pay_exceed_total_400(self, client, enterprise, db_session):
        bill = _make_bill(db_session, enterprise, status=BillStatus.CONFIRMED,
                          total=Decimal("100.00"))
        res = client.post(PAY_URL.format(bid=bill.id), json={"paid_amount": "100.01"})
        assert res.status_code == 400
        assert "不能超过" in res.json()["detail"]

    def test_pay_success_balance(self, client, enterprise, db_session):
        bill = _make_bill(db_session, enterprise, status=BillStatus.CONFIRMED,
                          total=Decimal("100.00"))
        res = client.post(PAY_URL.format(bid=bill.id), json={"paid_amount": "30.00"})
        assert res.status_code == 200, res.text
        body = res.json()["data"]
        assert body["status"] == "paid"
        assert Decimal(str(body["paid_amount"])) == Decimal("30.00")
        assert Decimal(str(body["balance_amount"])) == Decimal("70.00")

    def test_pay_not_found_404(self, client):
        res = client.post(PAY_URL.format(bid=99999999), json={"paid_amount": "1.00"})
        assert res.status_code == 404
        assert res.json()["detail"] == "账单不存在"
