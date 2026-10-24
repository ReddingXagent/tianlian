"""
资金边界守卫测试 · 第9弹 收口扫尾 (卡58981c26)

覆盖剩余无守卫真资金字段, 全部补 ge=0 防负值入参污染资金计算:
- fleet_drivers AccountRechargeRequest.amount / TransactionCreateRequest.amount
- enterprise_transactions TransactionCreateRequest.amount
- operate/interconnect OrderCreate.charge_energy_kwh / .total_amount
- admin_interconnect OrderCreate.charge_energy_kwh / .total_amount
- operate/ops_settlement ReconciliationCreate.platform_amount / .payment_orders_count /
  .payment_amount + InterconnectSettlementCreate.total_amount
- operate/points_api PointsRecordCreate.balance_before
- charging_orders ChargingOrderCreate.charged_kwh
- vpp ResourceRegisterRequest.cost_per_kwh

difference_amount 不加守卫: 平台少收(负差异)是合法对账结果。
已跳过(既有更严守卫, 见交付说明): order_fees.RefundRequest(gt=0)、
enterprise_recharge.RechargeApplicationCreate(gt=0)、ops_invoice.InvoiceCreate(gt=0)、
parking_open.DiscountAppliedRequest(validator>0)。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.fleet_drivers import AccountRechargeRequest, TransactionCreateRequest
from app.api.v1.enterprise_transactions import (
    TransactionCreateRequest as EnterpriseTxCreate,
)
from app.api.v1.operate.interconnect import OrderCreate as OperateOrderCreate
from app.api.v1.admin_interconnect import OrderCreate as AdminOrderCreate
from app.api.v1.operate.ops_settlement import (
    ReconciliationCreate,
    InterconnectSettlementCreate,
)
from app.api.v1.operate.points_api import PointsRecordCreate
from app.api.v1.charging_orders import ChargingOrderCreate
from app.api.v1.vpp import ResourceRegisterRequest


class TestFleetDriversGuard:
    def test_negative_recharge_amount_rejected(self):
        with pytest.raises(ValidationError):
            AccountRechargeRequest(amount=-0.01)

    def test_zero_recharge_amount_accepted(self):
        assert AccountRechargeRequest(amount=0).amount == 0

    def test_negative_tx_amount_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreateRequest(type="consume", amount=-1.0)

    def test_zero_tx_amount_accepted(self):
        assert TransactionCreateRequest(type="refund", amount=0).amount == 0


class TestEnterpriseTransactionsGuard:
    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            EnterpriseTxCreate(type="recharge", amount=-0.01)

    def test_zero_amount_accepted(self):
        assert EnterpriseTxCreate(type="consume", amount=0).amount == 0


def _order_kwargs(**overrides):
    kwargs = dict(
        platform_id=1,
        platform_code="PLAT",
        outer_order_id="O1",
        charge_energy_kwh="12.50",
        total_amount="30.00",
    )
    kwargs.update(overrides)
    return kwargs


class TestInterconnectGuard:
    def test_operate_negative_energy_rejected(self):
        with pytest.raises(ValidationError):
            OperateOrderCreate(**_order_kwargs(charge_energy_kwh="-0.1"))

    def test_operate_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            OperateOrderCreate(**_order_kwargs(total_amount="-1"))

    def test_operate_zero_accepted(self):
        req = OperateOrderCreate(**_order_kwargs(charge_energy_kwh="0", total_amount="0"))
        assert req.charge_energy_kwh >= 0 and req.total_amount >= 0

    def test_admin_negative_energy_rejected(self):
        with pytest.raises(ValidationError):
            AdminOrderCreate(**_order_kwargs(charge_energy_kwh="-0.1"))

    def test_admin_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            AdminOrderCreate(**_order_kwargs(total_amount="-1"))

    def test_admin_zero_accepted(self):
        req = AdminOrderCreate(**_order_kwargs(charge_energy_kwh="0", total_amount="0"))
        assert req.charge_energy_kwh >= 0 and req.total_amount >= 0


class TestOpsSettlementGuard:
    def _recon_kwargs(self, **overrides):
        kwargs = dict(
            settlement_date="2026-08-01",
            payment_channel="wxpay",
            platform_amount="100.00",
            payment_orders_count=10,
            payment_amount="99.00",
        )
        kwargs.update(overrides)
        return kwargs

    def test_negative_platform_amount_rejected(self):
        with pytest.raises(ValidationError):
            ReconciliationCreate(**self._recon_kwargs(platform_amount="-1"))

    def test_negative_payment_orders_count_rejected(self):
        with pytest.raises(ValidationError):
            ReconciliationCreate(**self._recon_kwargs(payment_orders_count=-1))

    def test_negative_payment_amount_rejected(self):
        with pytest.raises(ValidationError):
            ReconciliationCreate(**self._recon_kwargs(payment_amount="-0.01"))

    def test_recon_zero_accepted(self):
        req = ReconciliationCreate(
            **self._recon_kwargs(platform_amount="0", payment_orders_count=0, payment_amount="0")
        )
        assert req.platform_amount >= 0 and req.payment_amount >= 0

    def test_interconnect_negative_total_amount_rejected(self):
        with pytest.raises(ValidationError):
            InterconnectSettlementCreate(
                platform_id="P1",
                start_date="2026-08-01",
                end_date="2026-08-31",
                total_amount="-1",
            )

    def test_interconnect_zero_total_amount_accepted(self):
        req = InterconnectSettlementCreate(
            platform_id="P1",
            start_date="2026-08-01",
            end_date="2026-08-31",
            total_amount="0",
        )
        assert req.total_amount >= 0


class TestPointsBalanceBeforeGuard:
    def test_negative_balance_before_rejected(self):
        with pytest.raises(ValidationError):
            PointsRecordCreate(
                user_id=1,
                record_type="earn",
                points=10,
                balance_before=-1,
            )

    def test_zero_balance_before_accepted(self):
        req = PointsRecordCreate(
            user_id=1, record_type="earn", points=10, balance_before=0
        )
        assert req.balance_before == 0


class TestChargingOrderGuard:
    def test_negative_charged_kwh_rejected(self):
        with pytest.raises(ValidationError):
            ChargingOrderCreate(station_id=1, device_id=1, charged_kwh=-0.1)

    def test_zero_charged_kwh_accepted(self):
        assert ChargingOrderCreate(station_id=1, device_id=1, charged_kwh=0).charged_kwh == 0


class TestVppCostGuard:
    def _res_kwargs(self):
        return dict(resource_id="R1", resource_type="battery", station_id="S1")

    def test_negative_cost_per_kwh_rejected(self):
        with pytest.raises(ValidationError):
            ResourceRegisterRequest(**self._res_kwargs(), cost_per_kwh=-0.1)

    def test_zero_cost_per_kwh_accepted(self):
        assert ResourceRegisterRequest(**self._res_kwargs(), cost_per_kwh=0).cost_per_kwh == 0
