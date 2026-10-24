# -*- coding: utf-8 -*-
"""
代码生成器服务测试 - 覆盖率补强 ≥70%

被测: app/services/code_generator.py (CodeGenerator + 全局单例 code_generator)
设计: 主流程走真测试库 (patched_db fixture), 覆盖序列递增 / 区域码回退 / 设备类型
      回退 / 批量生成 / 边界值 / 异常回滚 / 默认 db(SessionLocal) 路径;
      异常路径用 MagicMock 隔离 db.commit 抛错验证 rollback+raise。

模块级 SessionLocal 绑定坑 (与 test_maintenance_tasks / test_maintenance_schedule 同源):
  code_generator line 12 `from app.core.database import SessionLocal` 按值
  绑定到导入时对象, 绕过 conftest 对 db_module.SessionLocal 的覆盖 → 显式
  monkeypatch 模块属性 (patched_db fixture 内完成)。

覆盖:
- generate_team_code        正常 / 连续递增 / 指定区域 / 未知区域回退 / 默认db / 异常rollback
- generate_station_code     正常 / 未知区域回退 / 默认db / 异常rollback
- generate_gateway_sn       正常(6位序号) / 未知区域回退 / 默认db / 异常rollback
- generate_device_sn        各设备类型 / 未知类型回退PV / 未知区域回退 / 默认db /
                            charger_ac与dc共享CHG序列 / 异常rollback
- batch_generate_gateway_sn 正常 / 未知区域回退 / 边界(1,1000) / 非法count(0,-1,1001,5000) /
                            默认db / 异常rollback
- _get_or_create_sequence   新建分支 / 命中已有分支
- _next_value               连续递增
- code_generator 单例       smoke + 常量
"""
import pytest
from unittest.mock import MagicMock

from app.services import code_generator as code_gen_mod
from app.services.code_generator import CodeGenerator, code_generator
from app.models.code_sequence import CodeSequence


# ═══════════════════════════════════════════════════════════════
# Fixture
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def patched_db(test_db, monkeypatch):
    """注入测试库到 code_generator 模块 (绕过 from-import 按值绑定坑)。"""
    monkeypatch.setattr(code_gen_mod, "SessionLocal", test_db["SessionLocal"])
    return test_db


def _mock_db_commit_fails():
    """构造一个 mock db: 序列查询返回 None(走创建分支), commit 抛异常触发 except。

    仅 batch_generate_gateway_sn 仍保留内部 commit（调用方 generate_sn_codes 不 self-commit），
    其 *_rollback_on_exception 测试依赖此 helper。单条 generate_* 已删除内部 commit，
    改用 _mock_db_no_commit 验证「不提前 commit」契约。
    """
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.commit.side_effect = RuntimeError("commit failed")
    return db


def _mock_db_no_commit(next_value: int = 1):
    """构造一个 mock db: UPDATE...RETURNING 路径返回 next_value（序列已存在分支）。

    新契约：单条 generate_* 不再调用 db.commit() / db.rollback()。
    本 helper 模拟 _next_value 走 line 92-98 的 update().returning() 成功路径，
    供「不提前 commit」「不调用 rollback」契约测试使用。
    """
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = next_value  # _next_value line 98 命中, 直接返回
    db.execute.return_value = result
    return db


# ═══════════════════════════════════════════════════════════════
# generate_team_code
# ═══════════════════════════════════════════════════════════════
def test_generate_team_code_first_persists_sequence(patched_db):
    db = patched_db["session"]
    code = CodeGenerator.generate_team_code("HN", db=db)
    assert code == "THN0001"
    seq = db.query(CodeSequence).filter_by(key="seq:team:HN").one()
    assert seq.current_value == 1


def test_generate_team_code_sequential(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_team_code("HN", db=db) == "THN0001"
    assert CodeGenerator.generate_team_code("HN", db=db) == "THN0002"


def test_generate_team_code_explicit_region(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_team_code("GD", db=db) == "TGD0001"


def test_generate_team_code_unknown_region_fallback(patched_db):
    db = patched_db["session"]
    # 未知区域码 → 回退默认 HN
    assert CodeGenerator.generate_team_code("ZZ", db=db) == "THN0001"


def test_generate_team_code_default_db_path(patched_db):
    # db=None → 内部用模块 SessionLocal (已被 patched_db 注入测试库), finally close
    assert CodeGenerator.generate_team_code("HN", db=None) == "THN0001"


def test_generate_team_code_does_not_commit_caller_transaction():
    """新契约(卡0aec53a8缺陷2): 单条 generate_* 删除内部 commit/rollback,
    提交边界交由调用方控制。验证不提前 commit、不调用 rollback。"""
    db = _mock_db_no_commit(next_value=1)
    code = CodeGenerator.generate_team_code("HN", db=db)
    assert code == "THN0001"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# generate_station_code
# ═══════════════════════════════════════════════════════════════
def test_generate_station_code_first(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_station_code("HN", db=db) == "ZHN0001"


def test_generate_station_code_unknown_region_fallback(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_station_code("ZZ", db=db) == "ZHN0001"


def test_generate_station_code_default_db_path(patched_db):
    assert CodeGenerator.generate_station_code("HN", db=None) == "ZHN0001"


def test_generate_station_code_does_not_commit_caller_transaction():
    """新契约(卡0aec53a8缺陷2): 单条方法不操控调用方事务。"""
    db = _mock_db_no_commit(next_value=1)
    code = CodeGenerator.generate_station_code("HN", db=db)
    assert code == "ZHN0001"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# generate_gateway_sn
# ═══════════════════════════════════════════════════════════════
def test_generate_gateway_sn_first_six_digit_seq(patched_db):
    db = patched_db["session"]
    # 序号 6 位
    assert CodeGenerator.generate_gateway_sn("HN", db=db) == "GHN000001"


def test_generate_gateway_sn_unknown_region_fallback(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_gateway_sn("QQ", db=db) == "GHN000001"


def test_generate_gateway_sn_default_db_path(patched_db):
    assert CodeGenerator.generate_gateway_sn("HN", db=None) == "GHN000001"


def test_generate_gateway_sn_does_not_commit_caller_transaction():
    """新契约(卡0aec53a8缺陷2): 单条方法不操控调用方事务。"""
    db = _mock_db_no_commit(next_value=1)
    code = CodeGenerator.generate_gateway_sn("HN", db=db)
    assert code == "GHN000001"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# generate_device_sn
# ═══════════════════════════════════════════════════════════════
@pytest.mark.parametrize("device_type,expected", [
    ("pv_inverter", "DPV000001"),
    ("pcs", "DPCS000001"),
    ("battery", "DBAT000001"),
    ("charger_dc", "DCHG000001"),
    ("meter", "DMET000001"),
    ("gateway", "DGTW000001"),
])
def test_generate_device_sn_types(patched_db, device_type, expected):
    db = patched_db["session"]
    assert CodeGenerator.generate_device_sn(device_type, "HN", db=db) == expected


def test_generate_device_sn_unknown_type_fallback_pv(patched_db):
    db = patched_db["session"]
    # 未知设备类型 → 回退默认 PV
    assert CodeGenerator.generate_device_sn("nonexistent_type", "HN", db=db) == "DPV000001"


def test_generate_device_sn_unknown_region_fallback(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.generate_device_sn("pv_inverter", "BAD", db=db) == "DPV000001"


def test_generate_device_sn_default_db_path(patched_db):
    assert CodeGenerator.generate_device_sn("pv_inverter", "HN", db=None) == "DPV000001"


def test_generate_device_sn_charger_ac_shares_chg_sequence(patched_db):
    db = patched_db["session"]
    # charger_ac 与 charger_dc 均映射 CHG, 共享同一序列
    assert CodeGenerator.generate_device_sn("charger_dc", "HN", db=db) == "DCHG000001"
    assert CodeGenerator.generate_device_sn("charger_ac", "HN", db=db) == "DCHG000002"


def test_generate_device_sn_does_not_commit_caller_transaction():
    """新契约(卡0aec53a8缺陷2): 单条方法不操控调用方事务。"""
    db = _mock_db_no_commit(next_value=1)
    code = CodeGenerator.generate_device_sn("pv_inverter", "HN", db=db)
    assert code == "DPV000001"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# batch_generate_gateway_sn
# ═══════════════════════════════════════════════════════════════
def test_batch_generate_gateway_sn_normal(patched_db):
    db = patched_db["session"]
    codes = CodeGenerator.batch_generate_gateway_sn(3, "HN", db=db)
    assert codes == ["GHN000001", "GHN000002", "GHN000003"]


def test_batch_generate_gateway_sn_unknown_region_fallback(patched_db):
    db = patched_db["session"]
    codes = CodeGenerator.batch_generate_gateway_sn(2, "ZZ", db=db)
    assert codes == ["GHN000001", "GHN000002"]


def test_batch_generate_gateway_sn_min_boundary(patched_db):
    db = patched_db["session"]
    assert CodeGenerator.batch_generate_gateway_sn(1, "HN", db=db) == ["GHN000001"]


def test_batch_generate_gateway_sn_max_boundary(patched_db):
    db = patched_db["session"]
    codes = CodeGenerator.batch_generate_gateway_sn(1000, "HN", db=db)
    assert len(codes) == 1000
    assert codes[0] == "GHN000001"
    assert codes[-1] == "GHN001000"


def test_batch_generate_gateway_sn_default_db_path(patched_db):
    codes = CodeGenerator.batch_generate_gateway_sn(2, "HN", db=None)
    assert codes == ["GHN000001", "GHN000002"]


@pytest.mark.parametrize("bad_count", [0, -1, 1001, 5000])
def test_batch_generate_gateway_sn_invalid_count(patched_db, bad_count):
    db = patched_db["session"]
    with pytest.raises(ValueError, match="1-1000"):
        CodeGenerator.batch_generate_gateway_sn(bad_count, "HN", db=db)


def test_batch_generate_gateway_sn_rollback_on_exception():
    db = _mock_db_commit_fails()
    with pytest.raises(RuntimeError):
        CodeGenerator.batch_generate_gateway_sn(3, "HN", db=db)
    db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# 内部序列方法
# ═══════════════════════════════════════════════════════════════
def test_get_or_create_sequence_create_then_hit(patched_db):
    db = patched_db["session"]
    # 新建分支: 首次查询返回 None → 创建 current_value=0
    seq1 = CodeGenerator._get_or_create_sequence(db, "seq:test:k1")
    assert seq1.current_value == 0
    # 命中分支: 第二次查询返回已存在记录 (同一 identity map)
    seq2 = CodeGenerator._get_or_create_sequence(db, "seq:test:k1")
    assert seq2.key == "seq:test:k1"
    db.rollback()  # 清理 flush 未提交的创建


def test_next_value_increments(patched_db):
    db = patched_db["session"]
    assert CodeGenerator._next_value(db, "seq:test:k2") == 1
    assert CodeGenerator._next_value(db, "seq:test:k2") == 2
    assert CodeGenerator._next_value(db, "seq:test:k2") == 3
    db.rollback()


# ═══════════════════════════════════════════════════════════════
# 会话泄漏修复 (卡0aec53a8缺陷1): 无 db 调用时内部 session 必须 close
# ═══════════════════════════════════════════════════════════════
def test_default_db_session_is_closed_after_call(patched_db, monkeypatch):
    """db=None → 内部创建 session, finally 必须关闭。

    旧代码 `if not db: db = SessionLocal()` 重绑后 finally 条件 `if not db` 恒 False,
    内部 session 永不 close。修复后用 own_db 标记, finally 正确关闭。

    验证方式: monkeypatch 模块 SessionLocal 为返回包装 session 的工厂,
    包装 session 的 close 记录被调用。
    """
    import app.services.code_generator as cgm
    real_session_local = cgm.SessionLocal
    closed = []

    def _factory():
        s = real_session_local()
        orig_close = s.close

        def _tracked_close():
            closed.append(True)
            orig_close()

        s.close = _tracked_close
        return s

    monkeypatch.setattr(cgm, "SessionLocal", _factory)

    CodeGenerator.generate_team_code("HN", db=None)

    assert len(closed) == 1, "无 db 调用时内部创建的 session 必须被 close 恰好一次"


def test_explicit_db_not_closed_by_generator(patched_db):
    """调用方传入的 db 不应被生成器关闭 (生命周期归调用方)。"""
    db = patched_db["session"]
    CodeGenerator.generate_team_code("HN", db=db)
    # 调用方 session 仍可用 (未关闭) — 同 session 再调一次验证还活着
    CodeGenerator.generate_team_code("HN", db=db)


# ═══════════════════════════════════════════════════════════════
# 序号溢出校验 (卡0aec53a8缺陷3): 超 SEQ_LENGTHS 上限 raise ValueError
# ═══════════════════════════════════════════════════════════════
def _seed_sequence(db, key: str, value: int):
    """直接写入一条 CodeSequence (current_value=value) 预置溢出边界。"""
    from app.models.code_sequence import CodeSequence as CS
    db.add(CS(key=key, current_value=value))
    db.commit()


def test_team_code_overflow_raises(patched_db):
    """team 序号 4 位, 第 10000 个应 raise (不能生成 THN10000 破坏规格)。"""
    db = patched_db["session"]
    _seed_sequence(db, "seq:team:HN", 9999)
    # 第 10000 个: _next_value 返回 10000, zfill(4) → "10000" (5位) 违规
    with pytest.raises(ValueError, match="序号溢出|overflow"):
        CodeGenerator.generate_team_code("HN", db=db)


def test_station_code_overflow_raises(patched_db):
    db = patched_db["session"]
    _seed_sequence(db, "seq:station:HN", 9999)
    with pytest.raises(ValueError):
        CodeGenerator.generate_station_code("HN", db=db)


def test_gateway_sn_overflow_raises(patched_db):
    """gateway 序号 6 位, 第 1000001 个应 raise。"""
    db = patched_db["session"]
    _seed_sequence(db, "seq:gateway:HN", 999999)
    with pytest.raises(ValueError):
        CodeGenerator.generate_gateway_sn("HN", db=db)


def test_device_sn_overflow_raises(patched_db):
    db = patched_db["session"]
    _seed_sequence(db, "seq:device:HN:PV", 999999)
    with pytest.raises(ValueError):
        CodeGenerator.generate_device_sn("pv_inverter", "HN", db=db)


def test_batch_generate_gateway_sn_overflow_raises(patched_db):
    """批量: 单条溢出 (第N个序号超6位) 应 raise, 不返回变长码。"""
    db = patched_db["session"]
    _seed_sequence(db, "seq:gateway:HN", 999999)
    with pytest.raises(ValueError):
        CodeGenerator.batch_generate_gateway_sn(2, "HN", db=db)


def test_team_code_at_max_boundary_ok(patched_db):
    """边界: 序号 9999 (第9999个) 仍合法, 不溢出。"""
    db = patched_db["session"]
    _seed_sequence(db, "seq:team:HN", 9998)  # _next_value 返回 9999
    code = CodeGenerator.generate_team_code("HN", db=db)
    assert code == "THN9999"


# ═══════════════════════════════════════════════════════════════
# 并发安全: _next_value 原子 UPDATE
# ═══════════════════════════════════════════════════════════════
def test_next_value_concurrent_no_duplicates(patched_db):
    """并发生成的值必须全部唯一（SQLite 无行锁场景验证原子 UPDATE）。"""
    import threading
    db = patched_db["session"]
    results = []
    lock = threading.Lock()

    def worker():
        # 每个线程用独立 session 模拟并发
        from app.core.database import SessionLocal
        local_db = SessionLocal()
        try:
            val = CodeGenerator._next_value(local_db, "seq:test:conc")
            local_db.commit()
            with lock:
                results.append(val)
        finally:
            local_db.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert len(set(results)) == 8, f"重复值: {sorted(results)}"


# ═══════════════════════════════════════════════════════════════
# 单例 smoke
# ═══════════════════════════════════════════════════════════════
def test_singleton_and_constants():
    assert isinstance(code_generator, CodeGenerator)
    assert "HN" in CodeGenerator.REGIONS
    assert CodeGenerator.DEVICE_TYPES["pv_inverter"] == "PV"
    assert CodeGenerator.PREFIXES["team"] == "T"
    assert CodeGenerator.SEQ_LENGTHS["device"] == 6
