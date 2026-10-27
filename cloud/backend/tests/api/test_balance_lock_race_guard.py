#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金直写竞态加固回归测试 (卡 2b424102)。

覆盖 2 个端点:
- PUT /api/v1/enterprises/{id}       update_enterprise (balance/credit_limit 直写)
- PUT /api/v1/fleet/funds/{id}       update_fund (balance 直写)

修复内容: 直写余额/额度前以 with_for_update().populate_existing() 行锁读,
消除并发 PUT 及 PUT vs 结算扣减之间的读-改-写丢更新窗口。生产 PostgreSQL 下
真正锁行; SQLite 测试环境下 with_for_update 为 no-op, 本套件验证行为契约不变:

(a) PUT balance 成功 200 且余额落库生效
(b) PUT credit_limit 成功 200 且额度生效 (enterprises)
(c) 负 balance → 422 (schema 层 ge=0 前置拦截, 不触库)
(d) 不存在 id → 404 (含仅传 balance 的锁行 404 分支)
"""
from decimal import Decimal

import pytest

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.fund_pool import FundPool, FundAccountStatus

ENT_URL = "/api/v1/enterprises/{eid}"
FUND_URL = "/api/v1/fleet/funds/{fid}"


@pytest.fixture
def enterprise(db_session):
    ent = Enterprise(
        name="锁竞态测试企业", code="RACE-LOCK-ENT",
        status=EnterpriseStatus.ACTIVE,
        balance=Decimal("100.00"), credit_limit=Decimal("0.00"),
    )
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent


@pytest.fixture
def fund(db_session):
    pool = FundPool(
        account_name="锁竞态资金账户", account_type="运营账户",
        balance=Decimal("50.00"), status=FundAccountStatus.ACTIVE,
    )
    db_session.add(pool)
    db_session.commit()
    db_session.refresh(pool)
    return pool


# ───────────────────────── enterprises PUT ─────────────────────────

class TestUpdateEnterpriseBalanceLock:
    def test_put_balance_success(self, client, enterprise):
        res = client.put(
            ENT_URL.format(eid=enterprise.id), json={"balance": 888.5}
        )
        assert res.status_code == 200, res.text
        body = res.json()["data"]
        assert body["balance"] == pytest.approx(888.5)

    def test_put_credit_limit_success(self, client, enterprise):
        res = client.put(
            ENT_URL.format(eid=enterprise.id), json={"credit_limit": 200.0}
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["credit_limit"] == pytest.approx(200.0)

    def test_put_negative_balance_422(self, client, enterprise):
        res = client.put(
            ENT_URL.format(eid=enterprise.id), json={"balance": -1.0}
        )
        assert res.status_code == 422

    def test_put_balance_not_found_404(self, client):
        res = client.put("/api/v1/enterprises/99999999", json={"balance": 1.0})
        assert res.status_code == 404
        assert res.json()["detail"] == "企业账户不存在"


# ───────────────────────── fleet funds PUT ─────────────────────────

class TestUpdateFundBalanceLock:
    def test_put_balance_success(self, client, fund):
        res = client.put(
            FUND_URL.format(fid=fund.id), json={"balance": 666.25}
        )
        assert res.status_code == 200, res.text
        body = res.json()["data"]
        assert float(body["balance"]) == pytest.approx(666.25)

    def test_put_negative_balance_422(self, client, fund):
        res = client.put(FUND_URL.format(fid=fund.id), json={"balance": -0.01})
        assert res.status_code == 422

    def test_put_balance_not_found_404(self, client):
        res = client.put("/api/v1/fleet/funds/99999999", json={"balance": 1.0})
        assert res.status_code == 404
        assert res.json()["detail"] == "资金账户不存在"
