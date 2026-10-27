"""
测试编码生成器功能
"""
import pytest
from app.services.code_generator import CodeGenerator
from app.models.code_sequence import CodeSequence


def test_code_generator_basic(test_db):
    """测试基本编码生成功能"""
    db = test_db["session"]

    # 测试团队编码生成
    team_code1 = CodeGenerator.generate_team_code('HN', db)
    assert team_code1.startswith('T'), "团队编码应以T开头"
    assert len(team_code1) == 7, "团队编码应为7位"
    assert team_code1[1:3] == 'HN', "团队编码应包含区域码"

    # 测试站点编码生成
    station_code1 = CodeGenerator.generate_station_code('HN', db)
    assert station_code1.startswith('Z'), "站点编码应以Z开头"
    assert len(station_code1) == 7, "站点编码应为7位"

    # 测试网关SN生成
    gateway_sn1 = CodeGenerator.generate_gateway_sn('HN', db)
    assert gateway_sn1.startswith('G'), "网关SN应以G开头"
    assert len(gateway_sn1) == 9, "网关SN应为9位"

    # 测试设备SN生成
    device_sn1 = CodeGenerator.generate_device_sn('pv_inverter', 'HN', db)
    assert device_sn1.startswith('D'), "设备SN应以D开头"
    assert len(device_sn1) == 9, "设备SN应为9位"
    assert device_sn1[1:3] == 'PV', "光伏逆变器设备SN应包含PV类型码"

    # 测试批量生成
    batch_sns = CodeGenerator.batch_generate_gateway_sn(5, 'GD', db)
    assert len(batch_sns) == 5, "批量生成应返回指定数量的SN"
    for sn in batch_sns:
        assert sn.startswith('G'), "批量生成的SN应以G开头"
        assert sn[1:3] == 'GD', "批量生成的SN应包含正确的区域码"

    print("所有基本测试通过!")


def test_code_sequence_uniqueness(test_db):
    """测试序列号唯一性"""
    db = test_db["session"]

    # 连续生成10个团队编码
    codes = []
    for _ in range(10):
        code = CodeGenerator.generate_team_code('HN', db)
        codes.append(code)

    # 检查是否所有编码都唯一
    assert len(codes) == len(set(codes)), "所有生成的编码应唯一"

    # 检查序列号是否递增
    seq_numbers = [int(code[3:]) for code in codes]
    for i in range(1, len(seq_numbers)):
        assert seq_numbers[i] > seq_numbers[i-1], "序列号应递增"

    print("序列号唯一性测试通过!")


def test_different_regions_independent(test_db):
    """测试不同区域的序列独立"""
    db = test_db["session"]

    # 生成河南团队编码
    hn_code1 = CodeGenerator.generate_team_code('HN', db)

    # 生成广东团队编码
    gd_code1 = CodeGenerator.generate_team_code('GD', db)

    # 再次生成河南团队编码
    hn_code2 = CodeGenerator.generate_team_code('HN', db)

    # 检查不同区域编码不同
    assert hn_code1[1:3] != gd_code1[1:3], "不同区域的编码应有不同的区域码"

    # 检查同区域编码序列递增
    hn_seq1 = int(hn_code1[3:])
    hn_seq2 = int(hn_code2[3:])
    assert hn_seq2 > hn_seq1, "同区域序列应递增"

    print("不同区域独立序列测试通过!")


def test_invalid_region_handling(test_db):
    """测试无效区域码处理"""
    db = test_db["session"]

    # 使用无效区域码
    invalid_code = CodeGenerator.generate_team_code('INVALID', db)

    # 应该使用默认区域码HN
    assert invalid_code[1:3] == 'HN', "无效区域码应使用默认HN"

    print("无效区域码处理测试通过!")


# ────────────── 深度补充测试 ──────────────

def test_team_code_multiple_regions(test_db):
    """各区域码生成首个团队编码: T + region + 0001。"""
    db = test_db["session"]
    for region in ["HN", "GD", "JS", "SD", "BJ", "SH"]:
        code = CodeGenerator.generate_team_code(region, db)
        assert code.startswith(f"T{region}"), f"{region} 编码前缀错误: {code}"
        assert code.endswith("0001"), f"{region} 首个序号应为0001: {code}"


def test_station_code_uniqueness_and_format(test_db):
    """站点编码连续生成: 唯一、递增、Z + 区域 + 4位序号。"""
    db = test_db["session"]
    codes = [CodeGenerator.generate_station_code("HN", db) for _ in range(5)]
    assert len(codes) == len(set(codes)), "站点编码应唯一"
    nums = [int(c[3:]) for c in codes]
    assert nums == sorted(nums) and len(set(nums)) == 5, "站点序号应递增"
    for c in codes:
        assert c[0] == "Z" and c[1:3] == "HN" and len(c) == 7


def test_gateway_sn_format_length_and_unique(test_db):
    """网关SN: G + 区域(2) + 序号(6) = 9位, 连续生成唯一递增。"""
    db = test_db["session"]
    codes = [CodeGenerator.generate_gateway_sn("GD", db) for _ in range(5)]
    assert len(set(codes)) == 5
    for c in codes:
        assert c.startswith("GGD") and len(c) == 9
    nums = [int(c[3:]) for c in codes]
    assert nums == sorted(nums)


def test_device_sn_type_code_mapping(test_db):
    """设备类型 → 类型码映射正确 (D + 类型码 + 6位序号)。

    注: 类型码长度不一致 (PV=2, 其余=3), 故总长度不固定, 只断前缀与序号。
    """
    db = test_db["session"]
    cases = [
        ("pv_inverter", "PV"),
        ("pcs", "PCS"),
        ("battery", "BAT"),
        ("charger_dc", "CHG"),
        ("charger_ac", "CHG"),
        ("meter", "MET"),
        ("gateway", "GTW"),
    ]
    for dtype, prefix in cases:
        code = CodeGenerator.generate_device_sn(dtype, "HN", db)
        assert code.startswith("D" + prefix), f"{dtype} 应映射为 D{prefix}, 实际 {code}"
        assert code[-6:].isdigit(), f"序号部分应为6位数字: {code}"


def test_device_sn_pv_length_is_nine(test_db):
    """PV 类型码2位 → DPV + 6位 = 9位 (符合注释规格)。"""
    code = CodeGenerator.generate_device_sn("pv_inverter", "HN", test_db["session"])
    assert len(code) == 9


def test_device_sn_unknown_type_defaults_pv(test_db):
    """未知设备类型 → 默认 PV 类型码。"""
    code = CodeGenerator.generate_device_sn("unknown_type", "HN", test_db["session"])
    assert code.startswith("DPV"), f"未知类型应回退 PV, 实际 {code}"


def test_device_sn_independent_sequence_per_type(test_db):
    """同区域不同设备类型序列互相独立 (各自从 000001 开始)。"""
    db = test_db["session"]
    pv1 = CodeGenerator.generate_device_sn("pv_inverter", "HN", db)   # DPV000001
    pcs1 = CodeGenerator.generate_device_sn("pcs", "HN", db)          # DPCS000001
    pv2 = CodeGenerator.generate_device_sn("pv_inverter", "HN", db)   # DPV000002
    assert pv1.endswith("000001") and pv1.startswith("DPV")
    assert pcs1.startswith("DPCS") and pcs1.endswith("000001"), "PCS 序列应独立从1开始"
    assert pv2.endswith("000002"), "PV 第二个应为000002"


def test_batch_generate_gateway_sn_unique_and_incremental(test_db):
    """批量生成网关SN: 数量正确、唯一、递增、格式正确。"""
    db = test_db["session"]
    codes = CodeGenerator.batch_generate_gateway_sn(5, "HN", db)
    assert len(codes) == 5
    assert len(set(codes)) == 5
    nums = [int(c[3:]) for c in codes]
    assert nums == sorted(nums)
    for c in codes:
        assert c.startswith("GHN") and len(c) == 9


def test_batch_generate_below_one_raises(test_db):
    """count < 1 → ValueError。"""
    with pytest.raises(ValueError):
        CodeGenerator.batch_generate_gateway_sn(0, "HN", test_db["session"])


def test_batch_generate_above_1000_raises(test_db):
    """count > 1000 → ValueError。"""
    with pytest.raises(ValueError):
        CodeGenerator.batch_generate_gateway_sn(1001, "HN", test_db["session"])


def test_sequence_current_value_persisted(test_db):
    """生成 N 次后, CodeSequence.current_value 持久化为 N。"""
    db = test_db["session"]
    for _ in range(3):
        CodeGenerator.generate_team_code("HN", db)
    seq = db.query(CodeSequence).filter(CodeSequence.key == "seq:team:HN").one()
    assert seq.current_value == 3


def test_get_or_create_sequence_creates_then_reuses(test_db):
    """_get_or_create_sequence: 首次创建(current_value=0), 再次复用同一条记录。"""
    db = test_db["session"]
    seq1 = CodeGenerator._get_or_create_sequence(db, "seq:team:ZZ")
    db.commit()
    assert seq1.key == "seq:team:ZZ"
    assert seq1.current_value == 0
    # 第二次应复用 (返回同一 key 的记录)
    seq2 = CodeGenerator._get_or_create_sequence(db, "seq:team:ZZ")
    assert seq2.key == "seq:team:ZZ"
    all_zz = db.query(CodeSequence).filter(CodeSequence.key == "seq:team:ZZ").all()
    assert len(all_zz) == 1, "同 key 序列不应重复创建"


def test_next_value_increments(test_db):
    """_next_value 每次 +1。"""
    db = test_db["session"]
    v1 = CodeGenerator._next_value(db, "seq:team:NX")
    v2 = CodeGenerator._next_value(db, "seq:team:NX")
    v3 = CodeGenerator._next_value(db, "seq:team:NX")
    assert (v1, v2, v3) == (1, 2, 3)


def test_invalid_region_defaults_hn_all_methods(test_db):
    """所有生成方法对无效区域码统一回退 HN。

    注: team/station/gateway 编码含区域码([1:3]==HN); device 编码格式为
    D+类型码+序号(不含区域码), 区域仅影响序列 key, 故只断言不抛异常 + 类型码正确。
    """
    db = test_db["session"]
    assert CodeGenerator.generate_team_code("XX", db)[1:3] == "HN"
    assert CodeGenerator.generate_station_code("XX", db)[1:3] == "HN"
    assert CodeGenerator.generate_gateway_sn("XX", db)[1:3] == "HN"
    # device: 区域回退后走 HN 序列, 编码仍为合法 DPVxxxxxx
    assert CodeGenerator.generate_device_sn("pv_inverter", "XX", db).startswith("DPV")


def test_serial_stress_no_conflict(test_db):
    """串行压力: 连续生成 100 个团队编码, 全唯一 + 序号连续 1..100 + 序列表正确。

    序列表(current_value 单调递增)是并发安全的基础设施 —— 生产 PostgreSQL 下
    配合 with_for_update 行锁即保证并发无冲突。此处串行验证机制本身正确。
    """
    db = test_db["session"]
    codes = [CodeGenerator.generate_team_code("HN", db) for _ in range(100)]
    assert len(set(codes)) == 100, "串行生成存在重复"
    nums = [int(c[3:]) for c in codes]
    assert nums == list(range(1, 101)), "序号应连续 1..100"
    seq = db.query(CodeSequence).filter(CodeSequence.key == "seq:team:HN").one()
    assert seq.current_value == 100


def test_unique_constraint_prevents_duplicate_sequence(test_db):
    """CodeSequence.key UNIQUE 约束兜底: 并发竞态时重复 INSERT 被数据库拒绝, 不产生脏数据。"""
    db = test_db["session"]
    db.add(CodeSequence(key="seq:team:DUP", current_value=0))
    db.commit()
    # 同 key 再次 INSERT 应被 UNIQUE 约束拒绝
    db.add(CodeSequence(key="seq:team:DUP", current_value=0))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_concurrent_generation_under_lock(test_db):
    """模拟生产行锁语义的并发生成: 互斥访问序列表 → 全部唯一无冲突。

    SQLite 无 SELECT FOR UPDATE 行锁, 真多线程会对 current_value 产生
    lost update (两事务读到同值→都+1→重复编码, 且 UNIQUE 仅在 key 上兜不住)。
    生产 PostgreSQL 下 with_for_update 真正锁行, 天然互斥。本测试用全局锁
    复现该互斥语义, 验证多线程调用框架 + 序列表机制在互斥访问下并发安全。

    卡0aec53a8缺陷2: 单条 generate_* 不再内部 commit。调用方(本测试 worker)
    须自行 commit, 否则跨 session 序列值不落库 → 重复编码。
    """
    import threading

    success = []
    list_lock = threading.Lock()
    gen_lock = threading.Lock()  # 复现 PostgreSQL with_for_update 的行锁互斥
    Sess = test_db["SessionLocal"]

    def worker(n):
        local = []
        for _ in range(n):
            with gen_lock:
                # 显式传测试库 session, 避免依赖子线程模块级 SessionLocal override
                s = Sess()
                try:
                    code = CodeGenerator.generate_team_code("HN", s)
                    s.commit()  # 调用方提交事务 (新契约: 提交边界归调用方)
                    local.append(code)
                finally:
                    s.close()
        with list_lock:
            success.extend(local)

    threads = [threading.Thread(target=worker, args=(5,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(success) == 20
    assert len(set(success)) == 20, "互斥访问下并发生成不应出现重复编码"
    # 用新 session 查询, 避免主测试 session 旧事务快照看不到线程内 commit
    Sess = test_db["SessionLocal"]
    fresh = Sess()
    try:
        seq = fresh.query(CodeSequence).filter(CodeSequence.key == "seq:team:HN").one()
        assert seq.current_value == 20
    finally:
        fresh.close()



if __name__ == "__main__":
    print("开始测试编码生成器...")
    print("=" * 60)

    test_code_generator_basic()
    test_code_sequence_uniqueness()
    test_different_regions_independent()
    test_invalid_region_handling()

    print("=" * 60)
    print("所有测试完成!")
