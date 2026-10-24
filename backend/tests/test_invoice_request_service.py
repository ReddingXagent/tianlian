#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动开票申请服务 - 隔离单元测试 (MagicMock 隔离 DB)

被测: app/services/invoice_request_service.py
设计: 纯逻辑方法直测; DB 依赖 (Session) 全部用 MagicMock 自链式 query 隔离,
       不触碰真实数据库; 通知钩子 (invoice_notification / wx_subscribe_msg) patch 隔离。
       upload_invoice_file 落盘操作用 tmp_path 隔离, 不污染真实 uploads/。

覆盖:
- 工具函数: _dump/_parse_order_ids, _amount_yuan_to_cents, _detect_file_type
- apply_invoice: 校验链 (空/抬头/税号/订单不存在/非本人/未支付/金额异常/重复申请)
                 + 去重保序 + TOCTOU 二次校验 + 金额汇总元→分
- list_user_invoices / get_user_invoice (签名 URL 仅 ISSUED)
- resend_invoice_email (状态/邮箱校验)
- list_ops_requests (team_scope_value None/非None)
- _get_ops_request (不存在/跨团队)
- upload_invoice_file (magic bytes/size/content_type/状态/落盘/commit失败清理/通知钩子)
- reject_invoice_request (状态/原因校验/通知钩子)
- get_invoice_for_download (仅 ISSUED 可下载)
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.charging_order import OrderPaymentStatus
from app.models.invoice_request import (
    InvoiceFileType,
    InvoiceMode,
    InvoiceRequestStatus,
    InvoiceTitleType,
)
from app.services import invoice_request_service as svc
from app.services.invoice_request_service import InvoiceError


# ─────────────────────────────────────────────────────────
# 辅助: 自链式 query mock
# ─────────────────────────────────────────────────────────

def _chain_query(result=None, *, scalar=False):
    """构造自链式 query mock: filter/order_by/offset/limit/in_ 都返回自身。

    result: .all()/.first()/.scalar()/.count() 的返回值。
    scalar=True 时 .first() 也返回 result(用于 _used_order_nos 的 .all 场景需另行配)。
    """
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.in_.return_value = q
    q.all.return_value = result or []
    q.first.return_value = result
    q.scalar.return_value = result
    q.count.return_value = result if isinstance(result, int) else 0
    return q


def _new_db(*queries):
    """db.query 顺序返回给定 query mock; 未配的 query 返回空链。

    多数被测函数多次调 db.query(不同模型); 这里按调用顺序匹配。
    """
    db = MagicMock()
    it = iter(queries)
    sentinel = object()

    def _query(_model=None, *args, **kwargs):
        return next(it, _chain_query(None))

    db.query.side_effect = _query
    db._it = it
    db._sentinel = sentinel
    return db


def _user(uid=7):
    u = MagicMock()
    u.id = uid
    return u


def _order(order_no="O1", *, user_id=7, station_id=10, paid_amount=Decimal("1.23"),
           payment_status=OrderPaymentStatus.PAID):
    o = MagicMock()
    o.order_no = order_no
    o.user_id = user_id
    o.station_id = station_id
    o.paid_amount = paid_amount
    o.payment_status = payment_status
    return o


def _invoice_req(*, status=InvoiceRequestStatus.PENDING, amount=100,
                 invoice_file_path=None, invoice_file_type=None,
                 invoice_file_name=None, team_id=5, applied_at=None,
                 reviewed_at=None, created_at=None, reject_reason=None,
                 req_id=1, user_id=7):
    r = MagicMock()
    r.id = req_id
    r.user_id = user_id
    r.team_id = team_id
    r.status = status
    r.amount = amount
    r.title_type = InvoiceTitleType.PERSONAL
    r.title_name = "张三"
    r.tax_number = None
    r.email = None
    r.remark = None
    r.order_ids = '["O1"]'
    r.invoice_mode = InvoiceMode.MANUAL
    r.invoice_file_path = invoice_file_path
    r.invoice_file_type = invoice_file_type
    r.invoice_file_name = invoice_file_name
    r.reviewed_by = None
    r.reviewed_at = reviewed_at
    r.reject_reason = reject_reason
    r.applied_at = applied_at or datetime(2026, 7, 1, tzinfo=timezone.utc)
    r.created_at = created_at or datetime(2026, 7, 1, tzinfo=timezone.utc)
    return r


# ═══════════════════════════════════════════════════════════
# 1. 工具函数纯逻辑
# ═══════════════════════════════════════════════════════════

def test_dump_order_ids_serializes_list():
    assert svc._dump_order_ids(["O1", "O2"]) == '["O1", "O2"]'


def test_parse_order_ids_empty_variants():
    assert svc._parse_order_ids(None) == []
    assert svc._parse_order_ids("") == []
    assert svc._parse_order_ids("not json") == []
    assert svc._parse_order_ids("{") == []
    # 非列表 (如 dict) → []
    assert svc._parse_order_ids('{"a": 1}') == []


def test_parse_order_ids_list():
    assert svc._parse_order_ids('["O1", 2, null]') == ["O1", "2", "None"]


def test_amount_yuan_to_cents_none():
    assert svc._amount_yuan_to_cents(None) == 0


def test_amount_yuan_to_cents_rounding():
    # 1.23 元 → 123 分; 0.005 → round half to even 在 Python 是银行家舍入,
    # 但 0.005*100=0.5 → round(0.5)=0 (even). 用 1.255 → 125.5 → round=126? 用明确值。
    assert svc._amount_yuan_to_cents(Decimal("1.23")) == 123
    assert svc._amount_yuan_to_cents(Decimal("0.01")) == 1
    assert svc._amount_yuan_to_cents(Decimal("100.00")) == 10000
    # 0.5 分 → 向偶: 0.005*100=0.5 → round(0.5)=0
    assert svc._amount_yuan_to_cents(Decimal("0.005")) == 0


def test_detect_file_type_all_formats():
    assert svc._detect_file_type(b"%PDF-1.4...") == InvoiceFileType.PDF
    assert svc._detect_file_type(b"\x89PNG\r\n...") == InvoiceFileType.IMAGE
    assert svc._detect_file_type(b"\xff\xd8\xff\xe0...") == InvoiceFileType.IMAGE
    assert svc._detect_file_type(b"PK\x03\x04...") == InvoiceFileType.OFD


def test_detect_file_type_unknown():
    assert svc._detect_file_type(b"plain text no magic") is None
    assert svc._detect_file_type(b"") is None


# ═══════════════════════════════════════════════════════════
# 2. apply_invoice — 校验链
# ═══════════════════════════════════════════════════════════

def test_apply_invoice_empty_order_ids():
    db = _new_db()
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), [], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 422


def test_apply_invoice_all_empty_after_dedup():
    """order_ids 全为空字符串/None → 去重后为空 → 422。"""
    db = _new_db()
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["", None], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 422


def test_apply_invoice_title_name_empty():
    db = _new_db()
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "   ")
    assert "抬头" in ei.value.message
    assert ei.value.status == 422


def test_apply_invoice_company_requires_tax_number():
    db = _new_db()
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.COMPANY, "公司", tax_number="")
    assert "税号" in ei.value.message
    assert ei.value.status == 422


def test_apply_invoice_order_not_found():
    # _used_order_nos(空) + ChargingOrder 批量查询(返回空列表, order_map 空 → 订单不存在)
    db = _new_db(_chain_query([]), _chain_query([]))
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 404
    assert "不存在" in ei.value.message


def test_apply_invoice_order_not_owner_treated_as_not_found():
    """他人订单 → 统一报「不存在」, 不泄露存在性。"""
    # used(空) + ChargingOrder 批量(含他人订单) + Station 批量(取 team_id)
    db = _new_db(_chain_query([]), _chain_query([_order(user_id=999)]), _chain_query([]))
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(uid=7), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 404


def test_apply_invoice_order_unpaid():
    db = _new_db(
        _chain_query([]),  # _used_order_nos
        _chain_query([_order(payment_status=OrderPaymentStatus.UNPAID)]),  # ChargingOrder 批量
        _chain_query([]),  # Station 批量
    )
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert "未支付" in ei.value.message
    assert ei.value.status == 422


def test_apply_invoice_paid_amount_none_rejected():
    """PAID 但 paid_amount=None (DB 层脏数据) → 显式拒绝, 不静默开 0 元发票。"""
    o = _order(paid_amount=None)
    db = _new_db(_chain_query([]), _chain_query([o]), _chain_query([]))
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert "金额异常" in ei.value.message
    assert ei.value.status == 422


def test_apply_invoice_order_already_used():
    """订单已在 PENDING/ISSUED 申请中 → 409 重复。"""
    used = MagicMock()
    used.order_ids = '["O1"]'
    # used(含O1) + ChargingOrder 批量 + Station 批量 (校验在循环内, used 检查在状态之后)
    db = _new_db(_chain_query([used]), _chain_query([_order()]), _chain_query([]))
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 409
    assert "重复" in ei.value.message


def test_apply_invoice_dedup_preserves_order():
    """重复订单号去重保序, 金额按去重后订单汇总, 不重复计费。"""
    o1 = _order("O1", paid_amount=Decimal("1.00"))
    # 批量查询: used(空) → ChargingOrder 批量([o1]) → Station 批量([(10,5)]) → used 二次(空)
    # 去重在循环前, unique_ids=["O1"], 批量只拉到一张订单
    db = _new_db(
        _chain_query([]),          # 首次 _used_order_nos
        _chain_query([o1]),        # ChargingOrder 批量 for O1
        _chain_query([(10, 5)]),   # Station 批量 (station_id=10 → team_id=5)
        _chain_query([]),          # TOCTOU 二次 _used_order_nos
    )
    req = svc.apply_invoice(db, _user(), ["O1", "O1", "O1"],
                            InvoiceTitleType.PERSONAL, "张三")
    assert req.amount == 100   # 1.00 元 → 100 分, 仅计一次
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_apply_invoice_toctou_detects_concurrent_use():
    """TOCTOU: 首次检查通过, 但二次检查发现并发占用 → 409。"""
    # 二次 _used_order_nos 返回占用集合
    used2 = MagicMock()
    used2.order_ids = '["O1"]'
    db = _new_db(
        _chain_query([]),            # 首次 used: 空
        _chain_query([_order()]),    # ChargingOrder 批量
        _chain_query([(10, 5)]),     # Station 批量
        _chain_query([used2]),       # 二次 used: O1 已占用
    )
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 409


def test_apply_invoice_multi_order_amount_sum_and_company_tax_stripped():
    """多单金额汇总; company tax_number 去空白; email 去空白。

    卡 71062d84: 原断言 固化了「跨团队两单挂首单 team」缺陷行为 (10→5, 11→99
    仍取 team 5), 已翻转为同团队场景; 跨团队拒绝由下方专项测试覆盖。
    """
    o1 = _order("O1", paid_amount=Decimal("2.50"))
    o2 = _order("O2", paid_amount=Decimal("0.10"), station_id=11)

    db = _new_db(
        _chain_query([]),
        _chain_query([o1, o2]),         # ChargingOrder 批量 (两张订单)
        _chain_query([(10, 5), (11, 5)]),   # Station 批量 (同 team)
        _chain_query([]),
    )
    req = svc.apply_invoice(db, _user(), ["O1", "O2"],
                            InvoiceTitleType.COMPANY, "公司A",
                            tax_number=" 91100 00000 ",
                            email="  a@b.com  ", remark="备注")
    assert req.amount == 260                # 2.50 + 0.10 = 2.60 元 → 260 分
    assert req.team_id == 5                 # 同团队 → 单一 team
    assert req.tax_number == "91100 00000"  # strip 仅去首尾
    assert req.email == "a@b.com"
    assert req.status == InvoiceRequestStatus.PENDING
    assert req.invoice_mode == InvoiceMode.MANUAL


def test_apply_invoice_cross_team_orders_rejected():
    """卡 71062d84: 两单分属不同 team → 422 拒绝, 不落库 (原行为挂首单 team,
    另一团队运营在 team 隔离列表永不可见)。"""
    o1 = _order("O1", paid_amount=Decimal("2.50"))
    o2 = _order("O2", paid_amount=Decimal("0.10"), station_id=11)

    db = _new_db(
        _chain_query([]),
        _chain_query([o1, o2]),
        _chain_query([(10, 5), (11, 99)]),  # station 10→team5, 11→team99
        _chain_query([]),
    )
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1", "O2"],
                          InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 422
    assert "团队" in ei.value.message
    db.add.assert_not_called()


def test_apply_invoice_station_missing_rejected():
    """卡 71062d84: 订单 station 已删 (station→team 查不到) → 422,
    不产生 team_id=None 的平台孤儿申请 (团队级运营全部不可见)。"""
    o1 = _order("O1", paid_amount=Decimal("2.50"))

    db = _new_db(
        _chain_query([]),
        _chain_query([o1]),
        _chain_query([]),                # Station 批量: 查不到任何行
        _chain_query([]),
    )
    with pytest.raises(InvoiceError) as ei:
        svc.apply_invoice(db, _user(), ["O1"], InvoiceTitleType.PERSONAL, "张三")
    assert ei.value.status == 422
    assert "场站" in ei.value.message
    db.add.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 3. list_user_invoices / get_user_invoice
# ═══════════════════════════════════════════════════════════

def test_list_user_invoices_status_filter_and_paging():
    items = [_invoice_req(req_id=1), _invoice_req(req_id=2)]
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = items
    q.count.return_value = 2
    db = MagicMock()
    db.query.return_value = q

    res = svc.list_user_invoices(db, _user(), status="pending", page=2, page_size=5)
    assert res["total"] == 2
    assert res["page"] == 2
    assert res["page_size"] == 5
    assert [i["invoice_id"] for i in res["items"]] == [1, 2]
    # status filter 应被调用
    assert q.filter.called


def test_user_list_item_serialization():
    r = _invoice_req(req_id=42)
    d = svc._user_list_item(r)
    assert d["invoice_id"] == 42
    assert d["order_ids"] == ["O1"]
    assert d["title_type"] == "personal"
    assert d["status"] == "pending"
    assert d["applied_at"].startswith("2026-07-01")


def test_get_user_invoice_not_found():
    db = _new_db(_chain_query(None))
    with pytest.raises(InvoiceError) as ei:
        svc.get_user_invoice(db, _user(), 999, "http://x")
    assert ei.value.status == 404


def test_get_user_invoice_other_user_404():
    db = _new_db(_chain_query(_invoice_req(user_id=999)))
    with pytest.raises(InvoiceError) as ei:
        svc.get_user_invoice(db, _user(uid=7), 1, "http://x")
    assert ei.value.status == 404


def test_get_user_invoice_issued_has_file_info():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED,
                     invoice_file_path="uploads/invoices/a.pdf",
                     invoice_file_type=InvoiceFileType.PDF,
                     invoice_file_name="a.pdf")
    db = _new_db(_chain_query(r))
    with patch.object(svc.invoice_notification, "build_signed_file_url",
                      return_value="http://signed/url") as m:
        d = svc.get_user_invoice(db, _user(), 1, "http://base")
    assert m.called
    assert d["invoice_file"] == {
        "file_url": "http://signed/url",
        "file_type": "pdf",
        "file_name": "a.pdf",
    }
    # issued_at 取自 reviewed_at(_invoice_req 默认 None)
    assert d["issued_at"] is None


def test_file_info_dict_none_for_pending():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    assert svc._file_info_dict(r, "http://x") is None


def test_file_info_dict_none_for_issued_without_path():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED, invoice_file_path=None)
    assert svc._file_info_dict(r, "http://x") is None


# ═══════════════════════════════════════════════════════════
# 4. resend_invoice_email
# ═══════════════════════════════════════════════════════════

def test_resend_not_found():
    db = _new_db(_chain_query(None))
    with pytest.raises(InvoiceError) as ei:
        svc.resend_invoice_email(db, _user(), 1, "a@b.com")
    assert ei.value.status == 404


def test_resend_not_issued():
    db = _new_db(_chain_query(_invoice_req(status=InvoiceRequestStatus.PENDING)))
    with pytest.raises(InvoiceError) as ei:
        svc.resend_invoice_email(db, _user(), 1, "a@b.com")
    assert ei.value.status == 422
    assert "尚未开具" in ei.value.message


def test_resend_empty_email():
    db = _new_db(_chain_query(_invoice_req(status=InvoiceRequestStatus.ISSUED)))
    with pytest.raises(InvoiceError) as ei:
        svc.resend_invoice_email(db, _user(), 1, "   ")
    assert "邮箱" in ei.value.message


def test_resend_success_updates_email_and_sends():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED,
                     invoice_file_path="uploads/x.pdf")
    db = _new_db(_chain_query(r))
    with patch.object(svc.invoice_notification, "build_signed_file_url",
                      return_value="u"), \
         patch.object(svc.invoice_notification, "_build_issued_email_body",
                      return_value="body"), \
         patch.object(svc.invoice_notification, "send_invoice_email",
                      return_value=True) as send:
        ok = svc.resend_invoice_email(db, _user(), 1, "  new@x.com  ")
    assert ok is True
    assert r.email == "new@x.com"      # 去空白 + 更新
    db.commit.assert_called_once()
    send.assert_called_once()
    # 收件人为去空白后的邮箱
    assert send.call_args.args[0] == "new@x.com"


# ═══════════════════════════════════════════════════════════
# 4b. PUBLIC_BASE_URL 配置 (卡 283c1f12, 契约 §5.5)
# ═══════════════════════════════════════════════════════════

class TestPublicBaseUrl:
    """_noop_base 读 settings.PUBLIC_BASE_URL; 两条生产邮件路径
    (resend_invoice_email §5.3 / upload_invoice_file→ISSUED 通知 §5.5) 的
    下载链接指向配置域名而非硬编码假域名 tianlian.example (卡 283c1f12)。

    未配置 → 回退相对路径 + warning 告警运维 (契约只增不破, fallback 有显式测试)。
    build_signed_file_url 签名与 verify_file_token 2h 时效逻辑不变, 仅改 base 来源。
    """

    def test_noop_base_returns_configured_domain(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", "https://inv.tianlian.cn")
        assert svc._noop_base() == "https://inv.tianlian.cn"

    def test_noop_base_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", "https://inv.tianlian.cn/")
        assert svc._noop_base() == "https://inv.tianlian.cn"

    def test_noop_base_empty_and_warns_when_unconfigured(self, monkeypatch, caplog):
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", None)
        with caplog.at_level(logging.WARNING, logger=svc.logger.name):
            base = svc._noop_base()
        assert base == ""  # 回退相对路径, 不再硬编码假域名
        assert any("PUBLIC_BASE_URL" in r.message for r in caplog.records)

    def test_resend_email_body_uses_configured_domain(self, monkeypatch):
        """配置后补发邮件正文下载链接指向配置域名, 不含 tianlian.example。"""
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", "https://inv.tianlian.cn")
        r = _invoice_req(status=InvoiceRequestStatus.ISSUED,
                         invoice_file_path="uploads/x.pdf")
        db = _new_db(_chain_query(r))
        captured = {}

        def fake_send(to_email, subject, body, attachment_path=None):
            captured["body"] = body
            return True
        monkeypatch.setattr(svc.invoice_notification, "send_invoice_email", fake_send)
        # 真实 build_signed_file_url + _build_issued_email_body 运行 (端到端验证正文链接)
        ok = svc.resend_invoice_email(db, _user(), 1, "  new@x.com  ")
        assert ok is True
        body = captured["body"]
        assert "https://inv.tianlian.cn/api/v1/business/invoice-file?token=" in body
        assert "tianlian.example" not in body

    def test_resend_email_body_fallback_relative_no_fake_domain(self, monkeypatch, caplog):
        """未配置 → 补发邮件正文链接退化为相对路径, 不含假域名, 且告警运维。"""
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", None)
        r = _invoice_req(status=InvoiceRequestStatus.ISSUED,
                         invoice_file_path="uploads/x.pdf")
        db = _new_db(_chain_query(r))
        captured = {}

        def fake_send(to_email, subject, body, attachment_path=None):
            captured["body"] = body
            return True
        monkeypatch.setattr(svc.invoice_notification, "send_invoice_email", fake_send)
        with caplog.at_level(logging.WARNING, logger=svc.logger.name):
            svc.resend_invoice_email(db, _user(), 1, "new@x.com")
        body = captured["body"]
        assert "/api/v1/business/invoice-file?token=" in body  # 相对路径
        assert "tianlian.example" not in body
        assert any("PUBLIC_BASE_URL" in r.message for r in caplog.records)

    def test_upload_file_url_uses_configured_domain(self, tmp_path, monkeypatch):
        """配置后开票完成通知 file_url 指向配置域名 (邮件正文链接同源)。"""
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", "https://inv.tianlian.cn")
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        r = _invoice_req(status=InvoiceRequestStatus.PENDING)
        db = _new_db(_chain_query(r))
        monkeypatch.setattr(svc.wx_subscribe_msg, "resolve_openid", lambda *a, **kw: None)
        captured = {}

        def spy_notify(req, file_url=None, db=None, openid=None):
            captured["file_url"] = file_url
        monkeypatch.setattr(svc.invoice_notification, "notify_invoice_issued", spy_notify)
        svc.upload_invoice_file(db, _user(), 1, "f.pdf", b"%PDF-1.4", None, MagicMock())
        fu = captured["file_url"]
        assert fu.startswith("https://inv.tianlian.cn/api/v1/business/invoice-file?token=")
        assert "tianlian.example" not in fu

    def test_upload_file_url_fallback_relative_no_fake_domain(self, tmp_path, monkeypatch):
        """未配置 → 上传通知 file_url 退化为相对路径, 不含假域名。"""
        monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", None)
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        r = _invoice_req(status=InvoiceRequestStatus.PENDING)
        db = _new_db(_chain_query(r))
        monkeypatch.setattr(svc.wx_subscribe_msg, "resolve_openid", lambda *a, **kw: None)
        captured = {}

        def spy_notify(req, file_url=None, db=None, openid=None):
            captured["file_url"] = file_url
        monkeypatch.setattr(svc.invoice_notification, "notify_invoice_issued", spy_notify)
        svc.upload_invoice_file(db, _user(), 1, "f.pdf", b"%PDF-1.4", None, MagicMock())
        fu = captured["file_url"]
        assert fu.startswith("/api/v1/business/invoice-file?token=")  # 相对路径
        assert "tianlian.example" not in fu


# ═══════════════════════════════════════════════════════════
# 5. list_ops_requests / _get_ops_request
# ═══════════════════════════════════════════════════════════

def test_list_ops_platform_level_no_team_scope():
    items = [_invoice_req(req_id=1)]
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = items
    q.count.return_value = 1
    db = MagicMock()
    db.query.return_value = q
    res = svc.list_ops_requests(db, _user(), team_scope_value=None, status="pending")
    assert res["total"] == 1
    # team_scope None → 不应再 filter(仅 status filter)
    assert q.filter.call_count == 1


def test_list_ops_with_team_scope_filters_team():
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    q.count.return_value = 0
    db = MagicMock()
    db.query.return_value = q
    svc.list_ops_requests(db, _user(), team_scope_value=5, status=None)
    # team filter + 无 status filter → filter 调一次
    assert q.filter.call_count == 1


def test_ops_list_item_amount_yuan_conversion():
    r = _invoice_req(amount=260)
    d = svc._ops_list_item(r)
    assert d["amount_yuan"] == 2.6     # 260 分 → 2.60 元
    assert d["invoice_mode"] == "manual"


def test_ops_list_item_amount_yuan_zero_when_amount_falsy():
    r = _invoice_req(amount=0)
    d = svc._ops_list_item(r)
    assert d["amount_yuan"] == 0.0


def test_get_ops_request_not_found():
    db = _new_db(_chain_query(None))
    assert_team = MagicMock()
    with pytest.raises(InvoiceError) as ei:
        svc._get_ops_request(db, 99, _user(), assert_team)
    assert ei.value.status == 404
    assert_team.assert_not_called()    # 不存在则不校验 team


def test_get_ops_request_team_access_called():
    r = _invoice_req(team_id=5)
    db = _new_db(_chain_query(r))
    user = _user()
    assert_team = MagicMock()
    got = svc._get_ops_request(db, 1, user, assert_team)
    assert got is r
    assert_team.assert_called_once_with(user, 5)


# ═══════════════════════════════════════════════════════════
# 6. upload_invoice_file
# ═══════════════════════════════════════════════════════════

def test_upload_not_pending_rejected():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"%PDF",
                                "application/pdf", MagicMock())
    assert ei.value.status == 400


def test_upload_unsupported_content_type():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.upload_invoice_file(db, _user(), 1, "a.exe", b"%PDF",
                                "application/x-msdownload", MagicMock())
    assert "文件类型" in ei.value.message


def test_upload_empty_content():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"",
                                "application/pdf", MagicMock())
    assert "为空" in ei.value.message


def test_upload_oversize_file():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    big = b"%PDF" + b"x" * (svc.MAX_INVOICE_FILE_BYTES + 1)
    with pytest.raises(InvoiceError) as ei:
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", big,
                                "application/pdf", MagicMock())
    assert "10MB" in ei.value.message


def test_upload_magic_bytes_mismatch():
    """content_type 合法但内容头不匹配 → 校验失败。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"plain text",
                                "application/pdf", MagicMock())
    assert "校验失败" in ei.value.message


def test_upload_content_type_none_allowed():
    """content_type=None → 跳过软校验, 仅靠 magic bytes。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch("app.services.invoice_request_service.os.makedirs"), \
         patch("app.services.invoice_request_service.uuid.uuid4") as uid, \
         patch("builtins.open", create=True), \
         patch.object(svc.wx_subscribe_msg, "resolve_openid", return_value=None), \
         patch.object(svc.invoice_notification, "notify_invoice_issued") as notify:
        uid.return_value.hex = "deadbeef"
        got = svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"%PDF-1.4",
                                      None, MagicMock())
    assert got.status == InvoiceRequestStatus.ISSUED
    assert got.invoice_file_type == InvoiceFileType.PDF
    assert got.reviewed_by == 7
    assert got.reject_reason is None
    db.commit.assert_called_once()
    notify.assert_called_once()


@pytest.mark.parametrize("magic,expected", [
    (b"%PDF", InvoiceFileType.PDF),
    (b"\x89PNG", InvoiceFileType.IMAGE),
    (b"\xff\xd8\xff", InvoiceFileType.IMAGE),
    (b"PK\x03\x04", InvoiceFileType.OFD),
])
def test_upload_each_file_type_writes_correct_ext(tmp_path, magic, expected):
    """每种 magic bytes → 落盘扩展名正确 + status→ISSUED。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch.object(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path)), \
         patch.object(svc.wx_subscribe_msg, "resolve_openid", return_value=None), \
         patch.object(svc.invoice_notification, "notify_invoice_issued"):
        got = svc.upload_invoice_file(db, _user(), 1, "orig.name", magic,
                                      None, MagicMock())
    assert got.invoice_file_type == expected
    assert got.invoice_file_name == "orig.name"
    # 落盘文件存在且内容正确
    saved = list(tmp_path.glob("*"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == magic
    ext_map = {"pdf": "pdf", "ofd": "ofd", "image": "jpg"}
    assert saved[0].suffix == f".{ext_map[expected.value]}"


def test_upload_file_name_defaults_to_saved_name(tmp_path):
    """file_name=None → 用落盘文件名。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch.object(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path)), \
         patch.object(svc.wx_subscribe_msg, "resolve_openid", return_value=None), \
         patch.object(svc.invoice_notification, "notify_invoice_issued"):
        got = svc.upload_invoice_file(db, _user(), 1, None, b"%PDF",
                                      None, MagicMock())
    assert got.invoice_file_name is not None
    assert got.invoice_file_name.endswith(".pdf")


def test_upload_commit_failure_cleans_orphan_file_and_reraises(tmp_path):
    """commit 失败 → 清理已落盘文件, 不留磁盘孤儿, 并重抛。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    db.commit.side_effect = RuntimeError("db down")
    db.rollback = MagicMock()
    with patch.object(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path)), \
         pytest.raises(RuntimeError):
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"%PDF",
                                None, MagicMock())
    # 孤儿文件已被清理
    assert list(tmp_path.glob("*")) == []
    db.rollback.assert_called_once()


def test_upload_commit_failure_orphan_cleanup_swallows_oserror(tmp_path):
    """孤儿文件清理失败(os.remove 抛 OSError) → 仅记日志不掩盖原异常。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    db.commit.side_effect = RuntimeError("db down")
    db.rollback = MagicMock()
    with patch.object(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path)), \
         patch("app.services.invoice_request_service.os.remove",
               side_effect=OSError("boom")), \
         pytest.raises(RuntimeError):
        svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"%PDF",
                                None, MagicMock())


def test_upload_notification_hook_best_effort_does_not_block(tmp_path):
    """通知钩子抛异常 → 仅记日志, 主流程仍返回 ISSUED。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch.object(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path)), \
         patch.object(svc.wx_subscribe_msg, "resolve_openid",
                      side_effect=Exception("wx down")), \
         patch.object(svc.invoice_notification, "notify_invoice_issued",
                      side_effect=Exception("notify down")):
        got = svc.upload_invoice_file(db, _user(), 1, "a.pdf", b"%PDF",
                                      None, MagicMock())
    assert got.status == InvoiceRequestStatus.ISSUED


# ═══════════════════════════════════════════════════════════
# 7. reject_invoice_request
# ═══════════════════════════════════════════════════════════

def test_reject_not_pending():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.reject_invoice_request(db, _user(), 1, "原因", MagicMock())
    assert ei.value.status == 400


def test_reject_empty_reason():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with pytest.raises(InvoiceError) as ei:
        svc.reject_invoice_request(db, _user(), 1, "   ", MagicMock())
    assert "拒绝原因" in ei.value.message
    assert ei.value.status == 422


def test_reject_success_sets_status_and_notifies():
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch.object(svc.wx_subscribe_msg, "resolve_openid", return_value=None), \
         patch.object(svc.invoice_notification, "notify_invoice_rejected") as notify:
        got = svc.reject_invoice_request(db, _user(), 1, "  不合规  ", MagicMock())
    assert got.status == InvoiceRequestStatus.REJECTED
    assert got.reject_reason == "不合规"     # strip
    assert got.reviewed_by == 7
    db.commit.assert_called_once()
    notify.assert_called_once()


def test_reject_notification_hook_best_effort():
    """拒绝通知钩子异常 → 仅记日志, 主流程仍 REJECTED。"""
    r = _invoice_req(status=InvoiceRequestStatus.PENDING)
    db = _new_db(_chain_query(r))
    with patch.object(svc.wx_subscribe_msg, "resolve_openid",
                      side_effect=Exception("wx")), \
         patch.object(svc.invoice_notification, "notify_invoice_rejected",
                      side_effect=Exception("notify")):
        got = svc.reject_invoice_request(db, _user(), 1, "原因", MagicMock())
    assert got.status == InvoiceRequestStatus.REJECTED


# ═══════════════════════════════════════════════════════════
# 7b. void_invoice_request 通知钩子 (卡 9211f668 红冲三通道)
# ═══════════════════════════════════════════════════════════

def test_void_success_notifies():
    """红冲成功 → 调用 notify_invoice_voided, db/openid 透传, 在 return 前执行。"""
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED)
    r.voided = False  # MagicMock 显式置 False (否则 auto-attr 恒真误触发 400)
    db = _new_db(_chain_query(r))
    with patch.object(svc.wx_subscribe_msg, "resolve_openid",
                      return_value="oXyz"), \
         patch.object(svc.invoice_notification, "notify_invoice_voided") as notify:
        got = svc.void_invoice_request(db, _user(), 1, "  开票有误  ", MagicMock())
    assert got.voided is True
    assert got.void_reason == "开票有误"  # strip
    assert got.voided_by == 7
    db.commit.assert_called_once()
    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs.get("openid") == "oXyz"
    assert kwargs.get("db") is db
    assert notify.call_args.args == (got,)  # 传的是红冲后的同一申请单


def test_void_notification_hook_best_effort():
    """红冲通知钩子异常 (含 resolve_openid 异常) → 仅记日志, 主流程仍完成红冲。"""
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED)
    r.voided = False
    db = _new_db(_chain_query(r))
    with patch.object(svc.wx_subscribe_msg, "resolve_openid",
                      side_effect=Exception("wx")), \
         patch.object(svc.invoice_notification, "notify_invoice_voided",
                      side_effect=Exception("notify")):
        got = svc.void_invoice_request(db, _user(), 1, "原因", MagicMock())
    assert got.voided is True
    assert got.void_reason == "原因"
    db.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════
# 8. get_invoice_for_download
# ═══════════════════════════════════════════════════════════

def test_download_not_found_returns_none():
    db = _new_db(_chain_query(None))
    assert svc.get_invoice_for_download(db, 999) is None


def test_download_pending_returns_none():
    db = _new_db(_chain_query(_invoice_req(status=InvoiceRequestStatus.PENDING)))
    assert svc.get_invoice_for_download(db, 1) is None


def test_download_issued_returns_request():
    r = _invoice_req(status=InvoiceRequestStatus.ISSUED)
    db = _new_db(_chain_query(r))
    assert svc.get_invoice_for_download(db, 1) is r
