"""4 省购电价模板种子数据 — P1-4 任务A (卡片 P1-4)

⚠️ 示意值: 川/浙/粤/甘 4 省分时购电价为预研示意值, **上线前须按最新电网文件校准**。
   来源: 《光储充能量策略-实现预研.md》§5 + SPEC §5。

PeriodType 语义 (复用 pricing_v2.PeriodType):
- shoulder = 尖峰 (价最高, 夏冬季尖峰段)
- peak     = 高峰
- flat     = 平段
- valley   = 低谷 (甘肃午间光伏大发深谷)

数据结构 (与 tests/test_energy_strategy_api.py 同源, 单一真相源):
    SEED_PROVINCES = [
        {"province": "四川", "season_start": 6, "season_end": 10,
         "periods": [{"type": "peak", "start": (H,M), "end": (H,M), "price": 0.78}, ...]},
        ...
    ]
"""
from __future__ import annotations

from typing import Any

# ─── 4 省示意值 (上线前须按电网文件校准) ───
SEED_PROVINCES: list[dict[str, Any]] = [
    {  # 四川: 谷段长 (23-07 共 8h) / 价差中等 / 丰水期(6-10月)电价低
        "province": "四川", "season_start": 6, "season_end": 10,
        "periods": [
            {"type": "peak", "start": (10, 0), "end": (12, 0), "price": 0.78},
            {"type": "flat", "start": (7, 0), "end": (10, 0), "price": 0.55},
            {"type": "valley", "start": (23, 0), "end": (7, 0), "price": 0.32},
        ],
    },
    {  # 浙江: 高价差 / 双高峰 / 夏冬季尖峰(7-8月)
        "province": "浙江", "season_start": 7, "season_end": 8,
        "periods": [
            {"type": "shoulder", "start": (19, 0), "end": (21, 0), "price": 1.20},
            {"type": "peak", "start": (8, 0), "end": (11, 0), "price": 0.95},
            {"type": "valley", "start": (22, 0), "end": (8, 0), "price": 0.38},
        ],
    },
    {  # 广东: 尖峰电价高 / 夏季长峰段(7-9月)
        "province": "广东", "season_start": 7, "season_end": 9,
        "periods": [
            {"type": "shoulder", "start": (14, 0), "end": (17, 0), "price": 1.35},
            {"type": "peak", "start": (17, 0), "end": (21, 0), "price": 1.02},
            {"type": "valley", "start": (0, 0), "end": (6, 0), "price": 0.36},
        ],
    },
    {  # 甘肃: 谷段深(午间 09-16 光伏大发深谷 0.18) / 现货试点
        "province": "甘肃", "season_start": None, "season_end": None,
        "periods": [
            {"type": "peak", "start": (16, 0), "end": (22, 0), "price": 0.62},
            {"type": "flat", "start": (0, 0), "end": (9, 0), "price": 0.45},
            {"type": "valley", "start": (9, 0), "end": (16, 0), "price": 0.18},
        ],
    },
]

_SEED_PROVINCE_NAMES = tuple(p["province"] for p in SEED_PROVINCES)


def seed_energy_price_templates(session) -> dict:
    """幂等插入 4 省平台级 (team_id=NULL) 模板 + 时段明细。

    已存在的省份 (平台级同名模板) 跳过, 不重复插入。
    返回: {province: EnergyPriceTemplate} (含本轮新建 + 已存在的)。
    """
    from datetime import date, time
    from app.models.energy_strategy import EnergyPriceTemplate, EnergyPricePeriod
    from app.models.pricing_v2 import PeriodType

    result: dict[str, EnergyPriceTemplate] = {}
    for prov in SEED_PROVINCES:
        existing = session.query(EnergyPriceTemplate).filter(
            EnergyPriceTemplate.province == prov["province"],
            EnergyPriceTemplate.team_id.is_(None),
        ).order_by(EnergyPriceTemplate.version.desc()).first()
        if existing:
            result[prov["province"]] = existing
            continue

        tpl = EnergyPriceTemplate(
            province=prov["province"],
            version=1,
            effective_from=date(2026, 1, 1),
            effective_until=None,
            season_start_month=prov["season_start"],
            season_end_month=prov["season_end"],
            allow_export_to_grid=False,
            is_two_part_tariff=False,
            is_active=True,
            team_id=None,
        )
        session.add(tpl)
        session.flush()  # 取 tpl.id
        for p in prov["periods"]:
            session.add(EnergyPricePeriod(
                template_id=tpl.id,
                period_type=PeriodType(p["type"]),
                start_time=time(*p["start"]),
                end_time=time(*p["end"]),
                purchase_price=p["price"],
            ))
        session.commit()
        session.refresh(tpl)
        result[prov["province"]] = tpl
    return result


def unseed_energy_price_templates(session) -> int:
    """删除 4 省平台级 seed 模板 + 关联时段 (downgrade)。

    仅删 team_id IS NULL 的 seed 模板, 不影响团队级模板。
    返回删除的模板数。
    """
    from app.models.energy_strategy import EnergyPriceTemplate, EnergyPricePeriod

    tpl_ids = [row[0] for row in session.query(EnergyPriceTemplate.id).filter(
        EnergyPriceTemplate.province.in_(_SEED_PROVINCE_NAMES),
        EnergyPriceTemplate.team_id.is_(None),
    ).all()]
    if not tpl_ids:
        return 0
    session.query(EnergyPricePeriod).filter(
        EnergyPricePeriod.template_id.in_(tpl_ids)
    ).delete(synchronize_session=False)
    deleted = session.query(EnergyPriceTemplate).filter(
        EnergyPriceTemplate.id.in_(tpl_ids)
    ).delete(synchronize_session=False)
    session.commit()
    return int(deleted)
