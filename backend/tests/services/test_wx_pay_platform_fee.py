"""app/services/wx_pay/platform_fee.py 直接单元测试 (工作卡 7ca585f8)

现有 tests/api/test_ops_platform_fee.py (27 用例) 仅经 API 路由间接覆盖服务层;
本文件直接单测 service 函数, 不经 HTTP / 权限 / Pydantic 层:

- create_config: 全字段 + 默认值 + FeeScope 转换 + 持久化
- update_config: 字段白名单过滤 + rate_bp 校验 + scope 转换 + 部分更新 (仅传字段生效)
- to_dict: 序列化契约 (scope.value / user_ids None→[] / 时间 isoformat)
- _validate_rate_bp: 边界 0/3000 通过, 负数/>3000/None → InvalidFeeRate

注: get / delete 逻辑在路由层 (ops_platform_fee._get_cfg / db.delete) 内联,
service 层无对应函数, 故此两类不在此文件覆盖 (已由 API 测试覆盖)。
"""
import pytest

from app.models.platform_fee_config import PlatformFeeConfig, FeeScope
from app.services.wx_pay import platform_fee as svc
from app.services.wx_pay.platform_fee import InvalidFeeRate


# ─── 直接构造一条持久化配置 (绕过 create_config, 用于 update/serialize 测试) ───

def _make_config(
    db,
    *,
    team_id=1,
    tenant_id=None,
    enabled=False,
    rate_bp=0,
    scope="all",
    user_ids=None,
    note=None,
):
    cfg = PlatformFeeConfig(
        tenant_id=tenant_id,
        team_id=team_id,
        enabled=enabled,
        rate_bp=rate_bp,
        scope=FeeScope(scope),
        user_ids=user_ids,
        note=note,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


# ==================== _validate_rate_bp ====================

class TestValidateRateBp:
    """rate_bp ∈ [0, 3000]; 负数 / >3000 / None 抛 InvalidFeeRate。"""

    @pytest.mark.parametrize("rate", [0, 1, 1500, 3000])
    def test_valid_rates_pass(self, rate):
        # 不抛即通过
        svc._validate_rate_bp(rate)

    def test_negative_rejected(self):
        with pytest.raises(InvalidFeeRate):
            svc._validate_rate_bp(-1)

    def test_over_max_rejected(self):
        with pytest.raises(InvalidFeeRate):
            svc._validate_rate_bp(3001)

    def test_none_rejected(self):
        # Pydantic 层拦截 None, 此处兜底校验也必须拒绝
        with pytest.raises(InvalidFeeRate):
            svc._validate_rate_bp(None)

    def test_exception_message_carries_range(self):
        with pytest.raises(InvalidFeeRate, match=r"\[0, 3000\]"):
            svc._validate_rate_bp(-5)


# ==================== create_config ====================

class TestCreateConfig:
    def test_create_with_defaults(self, db_session):
        cfg = svc.create_config(db_session, team_id=7)
        assert cfg.id > 0
        assert cfg.team_id == 7
        assert cfg.tenant_id is None
        assert cfg.enabled is False          # 默认 false
        assert cfg.rate_bp == 0
        assert cfg.scope == FeeScope.ALL
        assert cfg.user_ids is None
        assert cfg.note is None

    def test_create_full_fields_persists(self, db_session):
        cfg = svc.create_config(
            db_session,
            team_id=2,
            tenant_id=99,
            enabled=True,
            rate_bp=200,
            scope="whitelist",
            user_ids=[11, 22],
            note="full",
        )
        assert cfg.tenant_id == 99
        assert cfg.enabled is True
        assert cfg.rate_bp == 200
        assert cfg.scope == FeeScope.WHITELIST
        assert cfg.user_ids == [11, 22]
        assert cfg.note == "full"
        # 持久化: 同一 session 重新查询能取回
        fetched = (
            db_session.query(PlatformFeeConfig)
            .filter(PlatformFeeConfig.id == cfg.id)
            .first()
        )
        assert fetched is not None
        assert fetched.rate_bp == 200

    def test_create_invalid_rate_raises(self, db_session):
        with pytest.raises(InvalidFeeRate):
            svc.create_config(db_session, team_id=1, rate_bp=-1)
        with pytest.raises(InvalidFeeRate):
            svc.create_config(db_session, team_id=1, rate_bp=3001)

    def test_create_boundary_rates_ok(self, db_session):
        c0 = svc.create_config(db_session, team_id=1, rate_bp=0)
        c3 = svc.create_config(db_session, team_id=1, rate_bp=3000)
        assert c0.rate_bp == 0
        assert c3.rate_bp == 3000

    def test_create_no_commit_on_invalid_rate(self, db_session):
        """rate 越界在校验阶段抛出, 不应落库脏配置。"""
        with pytest.raises(InvalidFeeRate):
            svc.create_config(db_session, team_id=1, rate_bp=-1)
        assert db_session.query(PlatformFeeConfig).count() == 0

    def test_create_team_id_none_allowed(self, db_session):
        # 平台级配置 team_id 可为 null
        cfg = svc.create_config(db_session, team_id=None, rate_bp=10)
        assert cfg.team_id is None


# ==================== update_config ====================

class TestUpdateConfig:
    def test_update_single_field(self, db_session):
        cfg = _make_config(db_session, rate_bp=100, note="orig")
        updated = svc.update_config(db_session, cfg, note="new-note")
        assert updated.note == "new-note"
        # 未传字段保持不变
        assert updated.rate_bp == 100

    def test_update_rate_bp_validated(self, db_session):
        cfg = _make_config(db_session, rate_bp=100)
        # 越界 → 抛 InvalidFeeRate 且原值不变
        with pytest.raises(InvalidFeeRate):
            svc.update_config(db_session, cfg, rate_bp=3001)
        with pytest.raises(InvalidFeeRate):
            svc.update_config(db_session, cfg, rate_bp=-1)
        # 正常更新
        svc.update_config(db_session, cfg, rate_bp=500)
        assert cfg.rate_bp == 500

    def test_update_scope_converts_to_enum(self, db_session):
        cfg = _make_config(db_session, scope="all")
        svc.update_config(db_session, cfg, scope="whitelist")
        assert cfg.scope == FeeScope.WHITELIST

    def test_update_user_ids_and_enabled(self, db_session):
        cfg = _make_config(db_session, enabled=False, user_ids=None)
        svc.update_config(db_session, cfg, enabled=True, user_ids=[1, 2])
        assert cfg.enabled is True
        assert cfg.user_ids == [1, 2]

    def test_update_tenant_id_allowed(self, db_session):
        # tenant_id 在白名单内, 可改
        cfg = _make_config(db_session, tenant_id=None)
        svc.update_config(db_session, cfg, tenant_id=55)
        assert cfg.tenant_id == 55

    def test_unknown_field_filtered(self, db_session):
        """非白名单字段被静默忽略 (continue), 不 setattr。"""
        cfg = _make_config(db_session, rate_bp=100)

        class NotAllowed:
            pass

        # id 不在白名单, 传了也不应被 setattr 到实例 (会破坏主键)
        svc.update_config(db_session, cfg, id=99999, rate_bp=200)
        # 主键未变, 白名单内字段生效
        assert cfg.id != 99999
        assert cfg.rate_bp == 200

    def test_update_rate_bp_validation_happens_before_scope_setattr(self, db_session):
        """同一调用里 rate_bp 越界应抛 (校验顺序: rate_bp 先于 scope 赋值)。"""
        cfg = _make_config(db_session, scope="all", rate_bp=0)
        with pytest.raises(InvalidFeeRate):
            svc.update_config(db_session, cfg, rate_bp=5000, scope="whitelist")

    def test_update_persists(self, db_session):
        cfg = _make_config(db_session, rate_bp=0)
        svc.update_config(db_session, cfg, rate_bp=777, note="persisted")
        db_session.expire_all()
        fetched = db_session.query(PlatformFeeConfig).filter_by(id=cfg.id).first()
        assert fetched.rate_bp == 777
        assert fetched.note == "persisted"


# ==================== to_dict ====================

class TestToDict:
    def test_full_serialization(self, db_session):
        cfg = _make_config(
            db_session,
            team_id=3,
            tenant_id=8,
            enabled=True,
            rate_bp=250,
            scope="whitelist",
            user_ids=[1, 2],
            note="ser",
        )
        d = svc.to_dict(cfg)
        assert d["id"] == cfg.id
        assert d["tenant_id"] == 8
        assert d["team_id"] == 3
        assert d["enabled"] is True
        assert d["rate_bp"] == 250
        assert d["scope"] == "whitelist"           # 取 .value
        assert d["user_ids"] == [1, 2]
        assert d["note"] == "ser"
        assert d["created_at"] is not None
        assert d["updated_at"] is not None

    def test_user_ids_none_to_empty_list(self, db_session):
        cfg = _make_config(db_session, user_ids=None)
        assert svc.to_dict(cfg)["user_ids"] == []

    def test_scope_serializes_to_string_value(self, db_session):
        cfg = _make_config(db_session, scope="all")
        assert svc.to_dict(cfg)["scope"] == "all"
        assert isinstance(svc.to_dict(cfg)["scope"], str)


# ==================== InvalidFeeRate 语义 ====================

class TestInvalidFeeRate:
    def test_is_distinct_exception(self):
        # InvalidFeeRate 是独立异常类, 非 ValueError 子类
        assert not issubclass(InvalidFeeRate, ValueError)
        assert issubclass(InvalidFeeRate, Exception)
