"""开票申请服务层测试 (用户端云端契约 §5, 工作卡 a09f8a21)

直接调 app/services/invoice_request_service.py, 不经 HTTP, 覆盖:
- apply_invoice: 正常/异常路径 + 金额汇总 + team_id 捕获 + 重复/重申 + paid_amount=None 守卫
- upload_invoice_file: 文件落盘 + 状态流转 + magic/size/content_type/state 校验
- reject_invoice_request: 状态流转 + 空 reason / 非 PENDING 校验
- _amount_yuan_to_cents: 元→分 单元

状态机: PENDING ──upload──▶ ISSUED; PENDING ──reject──▶ REJECTED (REJECTED 不占位, 可重申)。
金额: 元(Decimal) → 分(int), int(round(sum*100))。
"""
import os
import uuid
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.invoice_request import (
    InvoiceRequest,
    InvoiceRequestStatus,
    InvoiceTitleType,
    InvoiceFileType,
)
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole, Team
from app.services import invoice_request_service as svc
from app.services.invoice_request_service import InvoiceError


# ─── helpers (与 API 测试同源, 独立自包含) ───

def _add_user(session, username, role=UserRole.VIEWER, team_id=None):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(b"pw123456", bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _seed_station(session, *, team_id=None):
    st = Station(
        name=f"svc站{uuid.uuid4().hex[:4]}",
        code=f"SVCT{uuid.uuid4().hex[:6].upper()}",
        address="测试",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_order(
    session,
    *,
    user_id,
    station_id,
    paid_amount=Decimal("10.00"),
    payment_status=OrderPaymentStatus.PAID,
    device_id=1,
):
    o = ChargingOrder(
        order_no=f"ord_{uuid.uuid4().hex[:12]}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        paid_amount=paid_amount,
        payment_status=payment_status,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _admin(session):
    return session.query(User).filter(User.username == "admin").first()


@pytest.fixture
def ctx(client):
    """用户 + 团队站点 + 两张 PAID 订单 (10.00 / 5.50 元)。

    卡 71062d84: 开票申请要求订单场站挂 team (无 team 的申请对所有团队
    运营不可见, apply 已拒绝 team 缺失), 故 fixture 站点显式挂 team。
    """
    from app.models.user import Team
    s = client._sesh
    team = Team(name=f"svc队{uuid.uuid4().hex[:6]}", code=f"SVCC{uuid.uuid4().hex[:6].upper()}")
    s.add(team)
    s.commit()
    s.refresh(team)
    st = _seed_station(s, team_id=team.id)
    u = _add_user(s, f"svc_cu_{uuid.uuid4().hex[:6]}")
    o1 = _seed_order(s, user_id=u.id, station_id=st.id, paid_amount=Decimal("10.00"))
    o2 = _seed_order(s, user_id=u.id, station_id=st.id, paid_amount=Decimal("5.50"))
    return {"s": s, "u": u, "st": st, "team": team, "o1": o1, "o2": o2}


# ==================== apply_invoice (契约 §5.1) ====================

class TestApplyInvoice:
    def test_apply_normal_pending(self, ctx):
        r = svc.apply_invoice(
            ctx["s"], ctx["u"], [ctx["o1"].order_no], InvoiceTitleType.PERSONAL, "张三"
        )
        assert r.status == InvoiceRequestStatus.PENDING
        assert r.amount == 1000  # 10.00 元 → 1000 分
        assert r.user_id == ctx["u"].id
        assert r.title_name == "张三"

    def test_apply_multi_order_amount_sum(self, ctx):
        r = svc.apply_invoice(
            ctx["s"], ctx["u"],
            [ctx["o1"].order_no, ctx["o2"].order_no],
            InvoiceTitleType.PERSONAL, "张三",
        )
        assert r.amount == 1550  # 10.00 + 5.50

    def test_apply_company_requires_tax_number(self, ctx):
        with pytest.raises(InvoiceError) as e:
            svc.apply_invoice(
                ctx["s"], ctx["u"], [ctx["o1"].order_no],
                InvoiceTitleType.COMPANY, "某某公司",
            )
        assert e.value.status == 422

    def test_apply_unpaid_order_422(self, ctx):
        o = _seed_order(
            ctx["s"], user_id=ctx["u"].id, station_id=ctx["st"].id,
            payment_status=OrderPaymentStatus.UNPAID,
        )
        with pytest.raises(InvoiceError) as e:
            svc.apply_invoice(ctx["s"], ctx["u"], [o.order_no],
                              InvoiceTitleType.PERSONAL, "张三")
        assert e.value.status == 422

    def test_apply_order_not_owned_404(self, ctx):
        other = _add_user(ctx["s"], f"svc_other_{uuid.uuid4().hex[:6]}")
        o = _seed_order(ctx["s"], user_id=other.id, station_id=ctx["st"].id)
        with pytest.raises(InvoiceError) as e:
            svc.apply_invoice(ctx["s"], ctx["u"], [o.order_no],
                              InvoiceTitleType.PERSONAL, "张三")
        assert e.value.status == 404

    def test_apply_duplicate_pending_409(self, ctx):
        svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                          InvoiceTitleType.PERSONAL, "张三")
        with pytest.raises(InvoiceError) as e:
            svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                              InvoiceTitleType.PERSONAL, "张三")
        assert e.value.status == 409

    def test_apply_rejected_then_reapply_ok(self, ctx):
        """REJECTED 不占位 → 同单可重新申请。"""
        r = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                              InvoiceTitleType.PERSONAL, "张三")
        r.status = InvoiceRequestStatus.REJECTED
        ctx["s"].commit()
        r2 = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                               InvoiceTitleType.PERSONAL, "张三")
        assert r2.status == InvoiceRequestStatus.PENDING

    def test_apply_paid_amount_null_rejected_422(self, ctx):
        """PAID 但 paid_amount=NULL (绕过 ORM 的 DB 层脏数据) → 422 (卡4b14971e)。

        ORM 正常路径下 None 会被列 default 归零, 永不触发此守卫; 守卫防的是
        raw SQL / 历史迁移写入的真实 DB 层 NULL, 故须用 raw SQL 注入 NULL 验证。
        """
        from sqlalchemy import text
        o = _seed_order(ctx["s"], user_id=ctx["u"].id, station_id=ctx["st"].id)
        ctx["s"].execute(
            text("UPDATE charging_orders SET paid_amount = NULL WHERE id = :id"),
            {"id": o.id},
        )
        ctx["s"].commit()
        ctx["s"].expire_all()  # 清 identity map, 让 apply 重新从 DB 读到 NULL
        with pytest.raises(InvoiceError) as e:
            svc.apply_invoice(ctx["s"], ctx["u"], [o.order_no],
                              InvoiceTitleType.PERSONAL, "张三")
        assert e.value.status == 422

    def test_apply_team_id_captured_from_station(self, client):
        """申请 team_id 由订单 station.team_id 捕获 (供 /ops 隔离)。"""
        s = client._sesh
        h = uuid.uuid4().hex[:6]
        team = Team(name=f"svc队{h}", code=f"SVCT{h}")
        s.add(team)
        s.commit()
        s.refresh(team)
        st = _seed_station(s, team_id=team.id)
        u = _add_user(s, f"svc_tu_{h}")
        o = _seed_order(s, user_id=u.id, station_id=st.id)
        r = svc.apply_invoice(s, u, [o.order_no], InvoiceTitleType.PERSONAL, "张三")
        assert r.team_id == team.id


# ==================== upload_invoice_file (契约 §5.4) ====================

class TestUploadFile:
    """assert_team_access 由 router 注入; 测试用 admin (平台级豁免) + 恒通替身。"""

    @staticmethod
    def _allow(user, team_id):
        return None  # 恒通替身 (admin 视角)

    def _pending_req(self, ctx):
        return svc.apply_invoice(
            ctx["s"], ctx["u"], [ctx["o1"].order_no], InvoiceTitleType.PERSONAL, "张三"
        )

    def test_upload_saves_file_and_issued(self, ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        req = self._pending_req(ctx)
        admin = _admin(ctx["s"])
        r = svc.upload_invoice_file(
            ctx["s"], admin, req.id, "f.pdf", b"%PDF-1.4 fake", "application/pdf", self._allow
        )
        assert r.status == InvoiceRequestStatus.ISSUED
        assert r.invoice_file_type == InvoiceFileType.PDF
        assert r.reviewed_by == admin.id
        assert r.reject_reason is None  # ISSUED 清空拒绝原因
        assert os.path.exists(r.invoice_file_path)

    def test_upload_wrong_magic_400(self, ctx):
        req = self._pending_req(ctx)
        with pytest.raises(InvoiceError) as e:
            svc.upload_invoice_file(
                ctx["s"], _admin(ctx["s"]), req.id, "f.pdf",
                b"plain text", "application/pdf", self._allow,
            )
        assert e.value.status == 400

    def test_upload_oversize_400(self, ctx, monkeypatch):
        monkeypatch.setattr(svc, "MAX_INVOICE_FILE_BYTES", 10)
        req = self._pending_req(ctx)
        with pytest.raises(InvoiceError) as e:
            svc.upload_invoice_file(
                ctx["s"], _admin(ctx["s"]), req.id, "f.pdf",
                b"%PDF" + b"x" * 50, "application/pdf", self._allow,
            )
        assert e.value.status == 400

    def test_upload_bad_content_type_400(self, ctx):
        req = self._pending_req(ctx)
        with pytest.raises(InvoiceError) as e:
            svc.upload_invoice_file(
                ctx["s"], _admin(ctx["s"]), req.id, "f.exe",
                b"%PDF-1.4", "application/x-msdownload", self._allow,
            )
        assert e.value.status == 400

    def test_upload_non_pending_400(self, ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        req = self._pending_req(ctx)
        req.status = InvoiceRequestStatus.ISSUED
        ctx["s"].commit()
        with pytest.raises(InvoiceError) as e:
            svc.upload_invoice_file(
                ctx["s"], _admin(ctx["s"]), req.id, "f.pdf",
                b"%PDF-1.4", "application/pdf", self._allow,
            )
        assert e.value.status == 400

    def test_upload_detects_image_and_ofd(self, ctx, tmp_path, monkeypatch):
        """magic bytes 识别 jpg→IMAGE / OFD(PK zip)→OFD。"""
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        admin = _admin(ctx["s"])
        # JPEG
        o_jpg = _seed_order(ctx["s"], user_id=ctx["u"].id, station_id=ctx["st"].id)
        req_jpg = svc.apply_invoice(ctx["s"], ctx["u"], [o_jpg.order_no],
                                    InvoiceTitleType.PERSONAL, "张三")
        r_jpg = svc.upload_invoice_file(ctx["s"], admin, req_jpg.id, "f.jpg",
                                        b"\xff\xd8\xffdata", "image/jpeg", self._allow)
        assert r_jpg.invoice_file_type == InvoiceFileType.IMAGE
        # OFD
        o_ofd = _seed_order(ctx["s"], user_id=ctx["u"].id, station_id=ctx["st"].id)
        req_ofd = svc.apply_invoice(ctx["s"], ctx["u"], [o_ofd.order_no],
                                    InvoiceTitleType.PERSONAL, "张三")
        r_ofd = svc.upload_invoice_file(ctx["s"], admin, req_ofd.id, "f.ofd",
                                        b"PK\x03\x04data", "application/ofd", self._allow)
        assert r_ofd.invoice_file_type == InvoiceFileType.OFD

    def test_upload_notify_passes_file_url(self, ctx, tmp_path, monkeypatch):
        """卡 f4288442: 上传后 notify_invoice_issued 必须收到非 None 的 file_url,
        否则开票完成邮件正文不含发票下载链接。"""
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        req = self._pending_req(ctx)
        admin = _admin(ctx["s"])

        captured = {}
        def fake_notify(r, file_url=None, db=None, openid=None):
            captured["file_url"] = file_url
        monkeypatch.setattr(
            svc.invoice_notification, "notify_invoice_issued", fake_notify
        )
        build_calls = []
        orig_build = svc.invoice_notification.build_signed_file_url
        def spy_build(invoice_id, base_url):
            build_calls.append((invoice_id, base_url))
            return orig_build(invoice_id, base_url)
        monkeypatch.setattr(
            svc.invoice_notification, "build_signed_file_url", spy_build
        )

        svc.upload_invoice_file(
            ctx["s"], admin, req.id, "f.pdf", b"%PDF-1.4 fake",
            "application/pdf", self._allow,
        )
        # build_signed_file_url 被调用 (而非 file_url 默认 None)
        assert build_calls and build_calls[0][0] == req.id
        # 传给 notify 的 file_url 非 None
        assert captured["file_url"] is not None


# ==================== reject_invoice_request (契约 §5.4) ====================

class TestReject:
    @staticmethod
    def _allow(user, team_id):
        return None

    def test_reject_status_flow(self, ctx):
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")
        admin = _admin(ctx["s"])
        r = svc.reject_invoice_request(ctx["s"], admin, req.id, "材料不全", self._allow)
        assert r.status == InvoiceRequestStatus.REJECTED
        assert r.reject_reason == "材料不全"
        assert r.reviewed_by == admin.id

    def test_reject_whitespace_reason_422(self, ctx):
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")
        with pytest.raises(InvoiceError) as e:
            svc.reject_invoice_request(ctx["s"], _admin(ctx["s"]), req.id, "  ", self._allow)
        assert e.value.status == 422

    def test_reject_non_pending_400(self, ctx):
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")
        req.status = InvoiceRequestStatus.ISSUED
        ctx["s"].commit()
        with pytest.raises(InvoiceError) as e:
            svc.reject_invoice_request(ctx["s"], _admin(ctx["s"]), req.id, "x", self._allow)
        assert e.value.status == 400


# ==================== void_invoice_request (Phase2-B2 红冲, 卡 f42bdf5a) ====================

class TestVoid:
    """service 层红冲: 仅 ISSUED; R1 方案b —— status 三态不变, 打 voided 标记。"""

    @staticmethod
    def _allow(user, team_id):
        return None

    def _issued(self, ctx):
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")
        req.status = InvoiceRequestStatus.ISSUED
        req.invoice_file_path = "/tmp/fake.pdf"
        ctx["s"].commit()
        ctx["s"].refresh(req)
        return req

    def test_void_marks_voided_keeps_status(self, ctx):
        """红冲: voided=True + 审计三件套; status/reject_reason/金额/文件不动。"""
        req = self._issued(ctx)
        admin = _admin(ctx["s"])
        r = svc.void_invoice_request(ctx["s"], admin, req.id, "开票信息有误", self._allow)
        assert r.status == InvoiceRequestStatus.ISSUED  # 三态不变 (R1 方案b)
        assert r.voided is True
        assert r.void_reason == "开票信息有误"
        assert r.voided_by == admin.id
        assert r.voided_at is not None
        assert r.amount == 1000
        assert r.reject_reason is None
        assert r.invoice_file_path == "/tmp/fake.pdf"

    def test_void_new_request_defaults_voided_false(self, ctx):
        """新建申请默认未红冲 (voided=False)。"""
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")
        assert req.voided is False
        assert req.void_reason is None

    def test_void_non_issued_400(self, ctx):
        req = svc.apply_invoice(ctx["s"], ctx["u"], [ctx["o1"].order_no],
                                InvoiceTitleType.PERSONAL, "张三")  # PENDING
        with pytest.raises(InvoiceError) as e:
            svc.void_invoice_request(ctx["s"], _admin(ctx["s"]), req.id, "x", self._allow)
        assert e.value.status == 400

    def test_void_twice_400(self, ctx):
        """重复红冲 → 400 (锁非幂等, 首红冲记录不被覆盖)。"""
        req = self._issued(ctx)
        admin = _admin(ctx["s"])
        svc.void_invoice_request(ctx["s"], admin, req.id, "第一次", self._allow)
        ctx["s"].expire_all()
        with pytest.raises(InvoiceError) as e:
            svc.void_invoice_request(ctx["s"], admin, req.id, "第二次", self._allow)
        assert e.value.status == 400
        assert req.void_reason == "第一次"

    def test_void_empty_reason_422(self, ctx):
        req = self._issued(ctx)
        with pytest.raises(InvoiceError) as e:
            svc.void_invoice_request(ctx["s"], _admin(ctx["s"]), req.id, "  ", self._allow)
        assert e.value.status == 422

    def test_void_unknown_404(self, ctx):
        with pytest.raises(InvoiceError) as e:
            svc.void_invoice_request(ctx["s"], _admin(ctx["s"]), 999999, "x", self._allow)
        assert e.value.status == 404


# ==================== _amount_yuan_to_cents 单元 (契约 §6 分整数) ====================

class TestAmountYuanToCents:
    def test_none_to_zero(self):
        assert svc._amount_yuan_to_cents(None) == 0

    def test_yuan_to_cents(self):
        assert svc._amount_yuan_to_cents(Decimal("12.80")) == 1280

    def test_zero(self):
        assert svc._amount_yuan_to_cents(Decimal("0.00")) == 0

    def test_rounding(self):
        # 12.875 元 → 1287.5 分 → 四舍五入 1288
        assert svc._amount_yuan_to_cents(Decimal("12.875")) == 1288
