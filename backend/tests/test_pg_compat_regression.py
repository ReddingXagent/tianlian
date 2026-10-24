"""
PG 兼容性回归测试

覆盖两个仅在生产 PostgreSQL 暴露、SQLite 测试库无法触发的生产 500 bug:

- Bug1 (strftime SQLite 方言):
    operations_analytics 原用 func.strftime 截断时间, 而 strftime 是 SQLite 专有函数,
    PG 上报 `function strftime does not exist` (UndefinedFunction)。
    修复: _parse_range 同时给出 sqlite 与 pg 格式串, _build_period_expr 按 dialect
    选 func.strftime(SQLite) / func.to_char(PostgreSQL)。

- Bug2 (PG 枚举撞名 feetype):
    order_fee_item.FeeType(8 成员) 与 pricing_v2.FeeType(FIXED/PERCENT) 都用
    SAEnum(FeeType) 未指定 name -> PG 命名 enum 类型都叫 feetype, 先建者(service_fee_prices)
    占位, 仅含 FIXED/PERCENT; order_fee_items 插入 ELECTRICITY 报
    `invalid input value for enum feetype: "ELECTRICITY"`。
    修复: order_fee_item 的列改 SAEnum(FeeType, name="order_fee_type")。

这两类根因在 SQLite 测试库上都无法复现(SQLite 无独立命名 enum, 且 strftime 合法),
故现有 analytics/fee 集成测试(171 passed, 全 SQLite)无法守护, 在此补针对性回归。
"""
import pytest
from sqlalchemy import Column, DateTime, MetaData, Table
from sqlalchemy.dialects import postgresql, sqlite

from app.api.v1 import operations_analytics as oa
from app.models.order_fee_item import OrderFeeItem
from app.models.pricing_v2 import ServiceFeePrice


# ─── Bug1: 方言感知的时间截断 ───

class TestBug1DialectAwarePeriodLabel:
    """func.strftime 仅 SQLite 可用; PG 必须走 func.to_char"""

    def test_parse_range_returns_both_formats(self):
        """_parse_range 同时返回 sqlite 与 pg 两套格式串"""
        for rng in ("day", "week", "month", "year", "unknown"):
            start, end, sqlite_fmt, pg_fmt = oa._parse_range(rng)
            assert start < end
            assert sqlite_fmt and "%" in sqlite_fmt        # SQLite 占位符语法
            assert pg_fmt and "%" not in pg_fmt            # PG 用 YYYY/MM 风格

    @pytest.mark.parametrize("rng,sqlite_token,pg_token", [
        ("day", "%Y-%m-%d", "YYYY-MM-DD"),
        ("month", "%Y-%m", "YYYY-MM"),
        ("year", "%Y", "YYYY"),
    ])
    def test_parse_range_format_values(self, rng, sqlite_token, pg_token):
        """逐 range 校验格式串取值与文档一致"""
        _, _, sqlite_fmt, pg_fmt = oa._parse_range(rng)
        assert sqlite_fmt == sqlite_token
        assert pg_fmt == pg_token

    def test_parse_range_week_has_pg_iso_week(self):
        """week 的 PG 格式必须用 ISO 周 (IW), 对齐 SQLite 的 %W 语义"""
        _, _, _, pg_fmt = oa._parse_range("week")
        assert "IW" in pg_fmt and "IYYY" in pg_fmt

    def test_build_period_expr_pg_uses_to_char(self):
        """PG 方言编译结果含 to_char, 绝不含 strftime"""
        col = Table("t", MetaData(), Column("created_at", DateTime)).c.created_at
        expr = oa._build_period_expr("postgresql", col, "%Y-%m-%d", "YYYY-MM-DD")
        compiled = str(expr.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        assert "to_char" in compiled.lower()
        assert "strftime" not in compiled.lower()

    def test_build_period_expr_sqlite_uses_strftime(self):
        """SQLite 方言仍走 strftime, 不退化成 to_char"""
        col = Table("t", MetaData(), Column("created_at", DateTime)).c.created_at
        expr = oa._build_period_expr("sqlite", col, "%Y-%m-%d", "YYYY-MM-DD")
        compiled = str(expr.compile(dialect=sqlite.dialect()))
        assert "strftime" in compiled.lower()
        assert "to_char" not in compiled.lower()

    def test_build_period_expr_labels_period(self):
        """表达式带 'period' label, 供后续 .label/group_by 引用"""
        col = Table("t", MetaData(), Column("created_at", DateTime)).c.created_at
        for dialect in ("sqlite", "postgresql"):
            expr = oa._build_period_expr(dialect, col, "%Y-%m-%d", "YYYY-MM-DD")
            assert expr.name == "period"


# ─── Bug2: 枚举类型独立命名 ───

class TestBug2EnumNaming:
    """order_fee_items.fee_type 的 PG enum 类型必须独立命名, 不与 pricing_v2 撞"""

    def test_order_fee_item_enum_named_uniquely(self):
        """OrderFeeItem.fee_type 的 SAEnum name == order_fee_type (不再叫 feetype)"""
        assert OrderFeeItem.__table__.c.fee_type.type.name == "order_fee_type"

    def test_no_collision_with_pricing_feetype(self):
        """两个 fee_type 列的 PG enum 类型名必须不同, 否则后建者复用错误类型"""
        order_name = OrderFeeItem.__table__.c.fee_type.type.name
        pricing_name = ServiceFeePrice.__table__.c.fee_type.type.name
        assert order_name != pricing_name
        assert pricing_name == "feetype"   # pricing_v2 保持不动

    def test_pg_enum_labels_are_uppercase_member_names(self):
        """SAEnum 默认存枚举 NAME; PG type label 必须是 8 个大写 NAME, 与存储一致"""
        labels = set(OrderFeeItem.__table__.c.fee_type.type.enums)
        assert labels == {
            "ELECTRICITY", "SERVICE", "PARKING", "OCCUPANCY",
            "RESERVATION", "DISCOUNT", "COUPON", "POINTS",
        }
