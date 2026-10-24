#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InvoiceRequest 行为锁测试 — B1 合并安全网 (卡 6d06831d, 契约 v1.3 §5)

被锁对象: app/services/invoice_request_service.py (经真实 HTTP 路由全链路)。
定位: 与 tests/test_invoice_request_service.py (MagicMock 隔离单测) 及
tests/test_invoice_request.py / tests/api/test_ops_invoice_request.py (API 层)
互补 —— 本文件锁「一条链路穿到底」的行为契约, B1 下线旧 OpsInvoice 后任何
对新体系的回归在此第一时间暴露:

1. C端申请闭环: POST /business/invoices → ops /ops/invoice-requests 列表可见
2. 列表: 筛选 (status) / 分页 (page/page_size/total) / team 隔离 (跨 team 不可见)
3. upload → ISSUED 闭环: magic bytes 校验落盘 + issuer/issued_at 记录 (契约 §5.4)
   + C端详情可见 invoice_file (契约 §5.2)
4. reject 流程: 原因落库 + 状态迁移 + 用户可重申 (REJECTED 不占位)
5. 状态机非法迁移拒绝: ISSUED 后再 upload/reject 均 400; 不存在 → 404
6. 时区: 契约 v1.3 §6 ISO8601 带时区 — 列表/详情所有时间字段带 tz 后缀
"""
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import (
    ChargingOrder, OrderPaymentStatus, OrderStatus, UserType, PaymentMethod,
)
from app.models.invoice_request import InvoiceRequest, InvoiceRequestStatus
from app.models.station import Station, StationStatus
from app.models.user import Team, User, UserRole

import app.services.invoice_request_service as svc

BIZ_URL = "/api/v1/business/invoices"
OPS_URL = "/api/v1/ops/invoice-requests"


# ─── 脚手架 ─────────────────────────────────────────────────────────────────

def _login(client, username, password):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ctx(client):
    """完整场景: 两 team + 各一 operator + C端用户 + 场站 + PAID 订单 + token。

    h 前缀保证 user/station 唯一约束跨 test 不冲突。
    """
    s = client._sesh
    h = uuid.uuid4().hex[:6]

    ta = Team(name=f"锁链团队A{h}", code=f"BLA{h.upper()}")
    tb = Team(name=f"锁链团队B{h}", code=f"BLB{h.upper()}")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = f"pw{h}123456"

    def mk_user(name, team=None, role=UserRole.OPERATOR):
        u = User(
            username=f"{name}_{h}", real_name=name, role=role,
            team_id=team.id if team else None, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return u

    cu = mk_user("bl_cu", role=UserRole.VIEWER)              # C端申请人 (无 team)
    op_a = mk_user("bl_op_a", team=ta)                        # A 队运营
    op_b = mk_user("bl_op_b", team=tb)                        # B 队运营

    st = Station(
        name=f"锁链站{h}", code=f"BLST{h.upper()}", address="测试地址",
        status=StationStatus.NORMAL, team_id=ta.id,
    )
    s.add(st)
    s.commit()
    s.refresh(st)

    return {
        "s": s, "h": h, "ta": ta, "tb": tb, "cu": cu, "op_a": op_a, "op_b": op_b,
        "station": st,
        "cu_token": _login(client, f"bl_cu_{h}", pwd),
        "op_a_token": _login(client, f"bl_op_a_{h}", pwd),
        "op_b_token": _login(client, f"bl_op_b_{h}", pwd),
    }


def _make_order(ctx, order_no, paid_yuan, *, paid=True):
    """直接落一条充电订单 (PAID/UNPAID 由 paid 控制)。"""
    s = ctx["s"]
    o = ChargingOrder(
        order_no=order_no,
        station_id=ctx["station"].id,
        device_id=1,
        user_id=ctx["cu"].id,
        user_type=UserType.APP,
        total_amount=Decimal(str(paid_yuan)),
        paid_amount=Decimal(str(paid_yuan)),
        payment_status=(
            OrderPaymentStatus.PAID if paid else OrderPaymentStatus.UNPAID
        ),
        order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT,
    )
    s.add(o)
    s.commit()
    s.refresh(o)
    return o


def _apply(client, ctx, order_ids, *, title_type="personal",
           title_name="张三", tax_number=None):
    payload = {
        "order_ids": order_ids, "title_type": title_type,
        "title_name": title_name,
    }
    if tax_number:
        payload["tax_number"] = tax_number
    return client.post(BIZ_URL, json=payload, headers=_h(ctx["cu_token"]))


def _upload(client, ctx, req_id, *, content=b"%PDF-1.4 fake pdf",
            filename="f.pdf", content_type="application/pdf",
            token=None, tmp_path=None, monkeypatch=None):
    if tmp_path is not None and monkeypatch is not None:
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
    return client.post(
        f"{OPS_URL}/{req_id}/upload",
        files={"file": (filename, content, content_type)},
        headers=_h(token or ctx["op_a_token"]),
    )


def _reject(client, ctx, req_id, reason="材料不全", *, token=None):
    return client.post(
        f"{OPS_URL}/{req_id}/reject",
        json={"reject_reason": reason},
        headers=_h(token or ctx["op_a_token"]),
    )


def _biz_detail(client, ctx, invoice_id):
    return client.get(f"{BIZ_URL}/{invoice_id}", headers=_h(ctx["cu_token"]))


def _assert_tz(value, field):
    assert value, f"{field} 为空"
    assert value.endswith("+00:00") or value.endswith("Z"), (
        f"{field}={value} 缺时区后缀 (契约 v1.3 §6 ISO8601 带时区)"
    )


# ==================== 1. C端申请 → ops 处理链路闭环 ====================

class TestApplyToOpsPipeline:
    """C端 POST /business/invoices 产生的申请, 必须完整出现在 ops 侧。"""

    def test_apply_visible_in_ops_list(self, client, ctx):
        """C端申请 → A队运营列表可见 (team_id 由订单场站捕获)。"""
        o = _make_order(ctx, f"BL_ORD_1_{ctx['h']}", 128.00)
        r = _apply(client, ctx, [o.order_no])
        assert r.status_code == 202, r.text
        invoice_id = r.json()["data"]["invoice_id"]

        r2 = client.get(OPS_URL, headers=_h(ctx["op_a_token"]))
        assert r2.status_code == 200
        items = r2.json()["data"]["items"]
        match = [i for i in items if i["id"] == invoice_id]
        assert match, "C端申请未出现在归属团队运营的列表中"
        item = match[0]
        assert item["status"] == "pending"
        assert item["team_id"] == ctx["ta"].id
        assert item["amount"] == 12800        # 元 → 分 (契约 §6)
        assert item["amount_yuan"] == 128.0   # ops 侧预折算
        assert item["order_ids"] == [o.order_no]

    def test_apply_to_issued_to_user_detail_full_chain(self, client, ctx, tmp_path, monkeypatch):
        """全链路: 申请 → ops upload → C端详情含 invoice_file + issued_at。"""
        o = _make_order(ctx, f"BL_ORD_2_{ctx['h']}", 66.60)
        r = _apply(client, ctx, [o.order_no])
        invoice_id = r.json()["data"]["invoice_id"]

        up = _upload(client, ctx, invoice_id, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert up.status_code == 200, up.text
        d = up.json()["data"]
        assert d["status"] == "issued"
        assert d["issuer"] == ctx["op_a"].id          # 契约 §5.4 记录 issuer
        assert d["issued_at"]                          # + issued_at
        _assert_tz(d["issued_at"], "issued_at")

        detail = _biz_detail(client, ctx, invoice_id).json()["data"]
        assert detail["status"] == "issued"
        assert detail["invoice_file"], "ISSUED 后 C端详情必须返回 invoice_file (契约 §5.2)"
        assert detail["invoice_file"]["file_type"] == "pdf"
        assert detail["invoice_file"]["file_name"] == "f.pdf"
        _assert_tz(detail["issued_at"], "issued_at")

    def test_reject_then_user_sees_reason_and_can_reapply(self, client, ctx):
        """拒绝闭环: 原因落库 → C端可见 → 同订单可重新申请 (REJECTED 不占位)。"""
        o = _make_order(ctx, f"BL_ORD_3_{ctx['h']}", 30.00)
        r = _apply(client, ctx, [o.order_no])
        invoice_id = r.json()["data"]["invoice_id"]

        rj = _reject(client, ctx, invoice_id, reason="抬头信息不全")
        assert rj.status_code == 200, rj.text
        assert rj.json()["data"]["status"] == "rejected"

        detail = _biz_detail(client, ctx, invoice_id).json()["data"]
        assert detail["status"] == "rejected"
        assert detail["reject_reason"] == "抬头信息不全"

        # REJECTED 不占位 → 同订单重新申请成功 (契约 §5.4)
        r2 = _apply(client, ctx, [o.order_no])
        assert r2.status_code == 202, r2.text
        assert r2.json()["data"]["invoice_id"] != invoice_id


# ==================== 2. ops 列表: 筛选 / 分页 / team 隔离 ====================

class TestOpsList:
    def test_filter_by_status(self, client, ctx, tmp_path, monkeypatch):
        """status 筛选: pending/issued 互不混入。"""
        ids = []
        for i in range(3):
            o = _make_order(ctx, f"BL_ORD_F{i}_{ctx['h']}", 10.00 + i)
            ids.append(_apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"])
        # 第 1 条 upload → ISSUED
        _upload(client, ctx, ids[0], tmp_path=tmp_path, monkeypatch=monkeypatch)
        # 第 2 条 reject → REJECTED
        _reject(client, ctx, ids[1])

        r = client.get(
            OPS_URL, params={"status": "pending"}, headers=_h(ctx["op_a_token"])
        )
        got = {i["id"] for i in r.json()["data"]["items"]}
        assert ids[2] in got
        assert ids[0] not in got and ids[1] not in got

        r = client.get(
            OPS_URL, params={"status": "issued"}, headers=_h(ctx["op_a_token"])
        )
        got = {i["id"] for i in r.json()["data"]["items"]}
        assert ids[0] in got and ids[2] not in got

    def test_pagination(self, client, ctx):
        """分页: page_size=2 三页取尽, total 与种子一致。"""
        for i in range(5):
            o = _make_order(ctx, f"BL_ORD_P{i}_{ctx['h']}", 10.00)
            _apply(client, ctx, [o.order_no])

        all_ids = []
        for page in (1, 2, 3):
            r = client.get(
                OPS_URL, params={"page": page, "page_size": 2},
                headers=_h(ctx["op_a_token"]),
            )
            d = r.json()["data"]
            assert d["page"] == page
            assert d["page_size"] == 2
            if page == 1:
                assert d["total"] == 5
            all_ids.extend(i["id"] for i in d["items"])

        assert len(all_ids) == 5
        assert len(set(all_ids)) == 5  # 无重复无遗漏

    def test_team_isolation_and_admin_sees_all(self, client, ctx):
        """team 隔离: B队申请 A队运营不可见; admin (默认 token) 全可见。"""
        # C端申请挂在 A 队场站 → team_id = A
        o = _make_order(ctx, f"BL_ORD_T1_{ctx['h']}", 10.00)
        _apply(client, ctx, [o.order_no], title_name="A队申请")

        # 直接落一条 B 队申请 (无 B 队场站脚手架, 走 ORM 种子)
        s = ctx["s"]
        b_req = InvoiceRequest(
            order_ids=f'["BL_ORD_T2_{ctx["h"]}"]',
            user_id=ctx["cu"].id,
            team_id=ctx["tb"].id,
            title_type="personal",
            title_name="B队申请",
            amount=1000,
            status=InvoiceRequestStatus.PENDING,
        )
        s.add(b_req)
        s.commit()
        s.refresh(b_req)

        # A 队运营: 只见本队
        r = client.get(OPS_URL, headers=_h(ctx["op_a_token"]))
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert "A队申请" in names
        assert "B队申请" not in names

        # B 队运营: 只见本队
        r = client.get(OPS_URL, headers=_h(ctx["op_b_token"]))
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert "B队申请" in names
        assert "A队申请" not in names

        # admin (client 默认 token): 全可见
        r = client.get(OPS_URL)
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert {"A队申请", "B队申请"} <= names


# ==================== 3. 状态机: 非法迁移拒绝 ====================

class TestStateMachine:
    """3 态机 pending→issued/rejected; 终态后任何操作 400, 不存在 404。"""

    def test_upload_on_issued_rejected_with_400(self, client, ctx, tmp_path, monkeypatch):
        o = _make_order(ctx, f"BL_ORD_S1_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        _upload(client, ctx, invoice_id, tmp_path=tmp_path, monkeypatch=monkeypatch)

        # pending→issued 后再 upload: 非法迁移 → 400
        r = _upload(client, ctx, invoice_id, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert r.status_code == 400

    def test_reject_on_issued_rejected_with_400(self, client, ctx, tmp_path, monkeypatch):
        o = _make_order(ctx, f"BL_ORD_S2_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        _upload(client, ctx, invoice_id, tmp_path=tmp_path, monkeypatch=monkeypatch)

        r = _reject(client, ctx, invoice_id)
        assert r.status_code == 400

    def test_upload_on_rejected_400(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_S3_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        _reject(client, ctx, invoice_id)

        r = _upload(client, ctx, invoice_id)
        assert r.status_code == 400

    def test_reject_on_rejected_400(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_S4_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        _reject(client, ctx, invoice_id)

        r = _reject(client, ctx, invoice_id)
        assert r.status_code == 400

    def test_unknown_id_404(self, client, ctx, tmp_path, monkeypatch):
        r = _upload(client, ctx, 999999, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert r.status_code == 404
        r = _reject(client, ctx, 999999)
        assert r.status_code == 404

    def test_upload_cross_team_404(self, client, ctx):
        """跨 team 操作 → 404 (不泄露存在性)。"""
        o = _make_order(ctx, f"BL_ORD_S5_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        r = _upload(client, ctx, invoice_id, token=ctx["op_b_token"])
        assert r.status_code == 404
        r = _reject(client, ctx, invoice_id, token=ctx["op_b_token"])
        assert r.status_code == 404


# ==================== 4. 时区输出 (契约 v1.3 §6) ====================

class TestTimezoneOutput:
    """SQLite DateTime 列读回 naive → 序列化统一补 UTC; 防回归丢后缀。"""

    def test_ops_list_all_time_fields_have_tz(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_Z1_{ctx['h']}", 10.00)
        _apply(client, ctx, [o.order_no])

        r = client.get(OPS_URL, headers=_h(ctx["op_a_token"]))
        item = r.json()["data"]["items"][0]
        for field in ("applied_at", "created_at"):
            _assert_tz(item[field], field)

    def test_user_list_all_time_fields_have_tz(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_Z2_{ctx['h']}", 10.00)
        _apply(client, ctx, [o.order_no])

        r = client.get(BIZ_URL, headers=_h(ctx["cu_token"]))
        item = r.json()["data"]["items"][0]
        for field in ("applied_at", "reviewed_at", "created_at"):
            if item[field] is not None:
                _assert_tz(item[field], field)

    def test_rejected_detail_times_have_tz_and_reason_kept(self, client, ctx):
        """REJECTED 详情: reviewed_at 带时区 + reject_reason 落库原样返回。"""
        o = _make_order(ctx, f"BL_ORD_Z3_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        before = datetime.now(timezone.utc)
        _reject(client, ctx, invoice_id, reason="重复申请")
        after = datetime.now(timezone.utc)

        detail = _biz_detail(client, ctx, invoice_id).json()["data"]
        assert detail["reject_reason"] == "重复申请"
        _assert_tz(detail["reviewed_at"], "reviewed_at")
        # reviewed_at 真实落在 [before, after] 窗口内 (UTC)
        reviewed = datetime.fromisoformat(detail["reviewed_at"])
        assert before <= reviewed <= after

    def test_upload_writes_real_utctimestamp(self, client, ctx, tmp_path, monkeypatch):
        """issued_at 是本次 upload 真实时间而非旧值。"""
        o = _make_order(ctx, f"BL_ORD_Z4_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]
        before = datetime.now(timezone.utc)
        r = _upload(client, ctx, invoice_id, tmp_path=tmp_path, monkeypatch=monkeypatch)
        after = datetime.now(timezone.utc)

        issued = datetime.fromisoformat(r.json()["data"]["issued_at"])
        assert before <= issued <= after

        # DB 落盘的文件真实存在
        ctx["s"].expire_all()
        row = ctx["s"].query(InvoiceRequest).filter(
            InvoiceRequest.id == invoice_id).first()
        assert row.invoice_file_path and os.path.exists(row.invoice_file_path)


# ==================== 5. C端申请入口校验 (链路守卫) ====================

class TestApplyGuards:
    """B1 切换后 C端入口是唯一合法申请通道, 守卫不可放松。"""

    def test_apply_unpaid_order_rejected(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_G1_{ctx['h']}", 10.00, paid=False)
        r = _apply(client, ctx, [o.order_no])
        # 卡 418a675a: 业务错误 HTTP 200 + code!=0
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0

    def test_apply_duplicate_pending_conflict(self, client, ctx):
        """订单已在 PENDING 申请中 → 重复申请被拒。"""
        o = _make_order(ctx, f"BL_ORD_G2_{ctx['h']}", 10.00)
        assert _apply(client, ctx, [o.order_no]).status_code == 202
        r = _apply(client, ctx, [o.order_no])
        assert r.status_code == 200
        assert r.json()["code"] != 0

    def test_apply_company_requires_tax_number(self, client, ctx):
        o = _make_order(ctx, f"BL_ORD_G3_{ctx['h']}", 10.00)
        r = _apply(client, ctx, [o.order_no], title_type="company",
                   title_name="某公司")
        assert r.status_code == 422

    def test_status_values_are_lowercase(self, client, ctx):
        """契约 v1.3 §5 A1: status 统一小写。"""
        o = _make_order(ctx, f"BL_ORD_G4_{ctx['h']}", 10.00)
        invoice_id = _apply(client, ctx, [o.order_no]).json()["data"]["invoice_id"]

        r = client.get(BIZ_URL, headers=_h(ctx["cu_token"]))
        assert r.json()["data"]["items"][0]["status"] == "pending"

        _reject(client, ctx, invoice_id)
        detail = _biz_detail(client, ctx, invoice_id).json()["data"]
        assert detail["status"] == "rejected"
