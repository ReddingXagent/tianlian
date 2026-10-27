"""
司机账户余额并发竞态测试 - 卡 0020305d

缺口(对照基准 enterprise_balance_service.deduct_on_order_complete):
- recharge: 裸累加 (fleet_drivers.py:325) —— 无行锁, 基于读时快照计算
- consume: TOCTOU —— 余额检查(:395-399)与扣减(:405)之间无锁窗口, 双花透支
- total_spent: 裸累加(:419) 同窗口丢更新

SQLite 下 with_for_update() 为 no-op(已知), 故并发正确性断言用
双连接交错互commit后 stale 快照必被刷新(检测串行化, 参照卡674bb77e),
行锁语义本身用 query 对象 mock 断言。

方法: 绕过 TestClient, 直接构造双独立 Session 挂同一个底层文件 DB,
用 stub 替换 assert_enterprise_team_access/get_current_user,
以 db.commit() 为栅栏精确交错两个并发事务的读写时序。
"""
from decimal import Decimal

import pytest

import app.api.v1  # noqa: F401  先加载 api.v1, 避免 deps 循环导入 (卡 deps-team-scoping-guard)
from app.api.v1 import fleet_drivers as fd
from app.models.fleet_driver import (
    FleetDriver, FleetDriverAccount,
    DriverStatus, LicenseType, AccountStatus,
)
from app.models.user import User, UserRole


@pytest.fixture(autouse=True)
def _stub_access(monkeypatch):
    """打桩企业归属校验(本卡只测并发语义, 鉴权契约由 test_fleet_drivers.py 覆盖)。"""
    monkeypatch.setattr(fd, "assert_enterprise_team_access", lambda *a, **k: None)


@pytest.fixture
def _admin_user():
    return User(id=0, username="admin", role=UserRole.ADMIN, status="active", team_id=None)


@pytest.fixture
def enterprise_id(test_db):
    from app.models.enterprise import Enterprise
    s = test_db["session"]
    ent = Enterprise(name="并发测试企业", code="ENT_CONC_0020305D", balance=10000.00)
    s.add(ent)
    s.commit()
    s.refresh(ent)
    return ent.id


def _setup_driver_account(test_db, enterprise_id, balance="100.00",
                          total_spent="0.00"):
    """直连 DB 预置司机+账户, 返回 driver_id / account_id"""
    s = test_db["session"]
    driver = FleetDriver(
        enterprise_id=enterprise_id, name="并发司机", phone="13800138000",
        license_no="CONC0020305D", license_type=LicenseType.B2,
        status=DriverStatus.ACTIVE, total_spent=Decimal(total_spent),
    )
    s.add(driver)
    s.flush()
    account = FleetDriverAccount(
        driver_id=driver.id, balance=Decimal(balance),
        status=AccountStatus.ACTIVE,
    )
    s.add(account)
    s.commit()
    return driver.id, account.id


def _db_balance(test_db, account_id):
    s = test_db["session"]
    s.expire_all()
    acc = s.query(FleetDriverAccount).filter(
        FleetDriverAccount.id == account_id).first()
    return Decimal(acc.balance)


def _db_total_spent(test_db, driver_id):
    s = test_db["session"]
    s.expire_all()
    d = s.query(FleetDriver).filter(FleetDriver.id == driver_id).first()
    return Decimal(d.total_spent)


# ========== 集成: 双 session 串行化法(卡674bb77e同类) ==========
# 并发时序确定性复刻: B 先读账户固化陈旧 identity-map 快照(等价于并发事务
# 早先已读过该行), A 完整跑通路由并 commit, 再让 B 跑路由 ——
# 旧实现 B 基于陈旧快照计算(丢更新/双花), 行锁+持锁复查实现会强制刷新快照。

def test_recharge_lost_update_two_sessions(test_db, enterprise_id):
    """recharge 裸累加丢更新: balance=100, A、B 各充 10, 终态应 120。"""
    from app.api.v1.fleet_drivers import AccountRechargeRequest, recharge_account
    driver_id, account_id = _setup_driver_account(test_db, enterprise_id)
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()

    # B 先读账户 → identity map 固化 balance=100 陈旧快照
    acc_b = sb.query(FleetDriverAccount).filter(
        FleetDriverAccount.driver_id == driver_id).first()
    assert Decimal(acc_b.balance) == Decimal("100.00")

    # A 完整充值 +10 → DB=110
    recharge_account(driver_id, AccountRechargeRequest(amount=10),
                     db=sa, current_user=_admin_user)
    sa.commit()

    # B 充值: 旧实现用陈旧快照 100+10=110(丢 A 的 10); 正确=120
    recharge_account(driver_id, AccountRechargeRequest(amount=10),
                     db=sb, current_user=_admin_user)
    sb.commit()

    final = _db_balance(test_db, account_id)
    assert final == Decimal("120.00"), (
        f"并发充值丢更新: 期望 120.00, 实际 {final} (两笔各+10应都生效)")


def test_consume_double_spend_two_sessions(test_db, enterprise_id):
    """consume TOCTOU 双花: balance=100, A、B 各消费 80, 第二笔必须被拒。"""
    from fastapi import HTTPException
    from app.api.v1.fleet_drivers import TransactionCreateRequest, create_driver_transaction
    driver_id, account_id = _setup_driver_account(test_db, enterprise_id)
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()

    # B 固化陈旧快照 balance=100
    acc_b = sb.query(FleetDriverAccount).filter(
        FleetDriverAccount.driver_id == driver_id).first()
    assert Decimal(acc_b.balance) == Decimal("100.00")

    # A 完整消费 80 → DB=20
    create_driver_transaction(
        driver_id, TransactionCreateRequest(type="consume", amount=80),
        db=sa, current_user=_admin_user)
    sa.commit()

    # B 消费 80: 旧实现陈旧快照 100-80=20≥0 通过 → 双花(两笔各80只扣一次);
    # 持锁复查实现基于最新余额 20-80<0 → 400 余额不足
    with pytest.raises(HTTPException) as ei:
        create_driver_transaction(
            driver_id, TransactionCreateRequest(type="consume", amount=80),
            db=sb, current_user=_admin_user)
    assert ei.value.status_code == 400
    assert "余额不足" in ei.value.detail
    sb.rollback()

    final = _db_balance(test_db, account_id)
    assert final == Decimal("20.00"), f"双花透支: 期望 20.00, 实际 {final}"


def test_total_spent_lost_update_two_sessions(test_db, enterprise_id):
    """total_spent 裸累加丢更新: 双 consume 各 10, 终态应 20 而非 10。"""
    from app.api.v1.fleet_drivers import TransactionCreateRequest, create_driver_transaction
    driver_id, account_id = _setup_driver_account(
        test_db, enterprise_id, balance="500.00")
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()

    # B 固化 driver 陈旧快照 total_spent=0
    driver_b = sb.query(FleetDriver).filter(FleetDriver.id == driver_id).first()
    assert Decimal(driver_b.total_spent) == Decimal("0.00")

    # A 完整消费 10 → DB: balance=490, total_spent=10
    create_driver_transaction(
        driver_id, TransactionCreateRequest(type="consume", amount=10),
        db=sa, current_user=_admin_user)
    sa.commit()

    # B 消费 10: 旧实现 total_spent 用陈旧快照 0+10=10(丢 A 的一笔); 正确=20
    create_driver_transaction(
        driver_id, TransactionCreateRequest(type="consume", amount=10),
        db=sb, current_user=_admin_user)
    sb.commit()

    assert _db_balance(test_db, account_id) == Decimal("480.00")
    assert _db_total_spent(test_db, driver_id) == Decimal("20.00"), (
        f"total_spent 丢更新: 期望 20.00, 实际 {_db_total_spent(test_db, driver_id)}")


# ========== 语义单测: 行锁/持锁复查 (mock query) ==========

class _Recorder:
    def __init__(self, q):
        self.q = q
        self.saw_for_update = False
        self.saw_refresh_after_write = False


def _run_route_capture_queries(monkeypatch, test_db, enterprise_id, route, payload):
    """跑路由并捕获账户实体查询是否经 with_for_update() 构造。

    用 SQLAlchemy 事件监听对 fleet_driver_accounts 的 SELECT 语句,
    检查其编译产物是否含 FOR UPDATE (SQLite 编译器仍会渲染该子句,
    故可判断 query 构造语义, 不依赖数据库真实加锁)。
    """
    driver_id, account_id = _setup_driver_account(test_db, enterprise_id)
    from sqlalchemy import event
    from app.models.fleet_driver import FleetDriverAccount as FDA

    calls = {"for_update": 0, "plain": 0}
    mapping = {"account_id": account_id, "driver_id": driver_id}

    from sqlalchemy.orm import with_loader_criteria

    def _before_cursor_execute(conn, cursor, statement, parameters,
                               context, executemany):
        if "fleet_driver_accounts" not in statement:
            return
        comp = context.compiled
        sel = getattr(comp, "statement", None)
        # SQLite 方言不渲染 FOR UPDATE 文本, 从编译语句对象读 _for_update_arg
        if getattr(sel, "_for_update_arg", None) is not None:
            calls["for_update"] += 1
        else:
            calls["plain"] += 1

    engine = test_db["engine"]
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)

    sess = test_db["session"]
    result = {}
    try:
        result["r"] = route(driver_id, payload, db=sess, current_user=_admin_user)
    except BaseException as e:  # noqa: BLE001
        result["err"] = e
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)
        sess.rollback()
    return calls, result


def test_recharge_uses_row_lock(test_db, enterprise_id, monkeypatch):
    from app.api.v1.fleet_drivers import AccountRechargeRequest, recharge_account
    monkeypatch.setattr(fd, "assert_enterprise_team_access", lambda *a, **k: None)
    calls, result = _run_route_capture_queries(
        monkeypatch, test_db, enterprise_id, recharge_account,
        AccountRechargeRequest(amount=10))
    assert "err" not in result or not isinstance(result.get("err"), AssertionError)
    assert calls["for_update"] >= 1


def test_consume_uses_row_lock(test_db, enterprise_id, monkeypatch):
    from app.api.v1.fleet_drivers import TransactionCreateRequest, create_driver_transaction
    monkeypatch.setattr(fd, "assert_enterprise_team_access", lambda *a, **k: None)
    calls, result = _run_route_capture_queries(
        monkeypatch, test_db, enterprise_id, create_driver_transaction,
        TransactionCreateRequest(type="consume", amount=10))
    assert calls["for_update"] >= 1, "余额读取必须经 with_for_update() 行锁后复查"
    assert calls["for_update"] >= 1


def test_refund_uses_row_lock(test_db, enterprise_id, monkeypatch):
    from app.api.v1.fleet_drivers import TransactionCreateRequest, create_driver_transaction
    monkeypatch.setattr(fd, "assert_enterprise_team_access", lambda *a, **k: None)
    calls, result = _run_route_capture_queries(
        monkeypatch, test_db, enterprise_id, create_driver_transaction,
        TransactionCreateRequest(type="refund", amount=10))
    assert calls["for_update"] >= 1, "退款余额读取必须经 with_for_update() 行锁"
    assert calls["for_update"] >= 1
