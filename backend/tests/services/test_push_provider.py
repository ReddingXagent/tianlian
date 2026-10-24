"""PushProvider 抽象与发票 App 推送走默认日志实现 (卡 d95dafd3).

卡 5a280e1a 补齐: 发送链路按用户 device tokens 分发 (openid → end_users → tokens)。
"""

import logging
import threading
import time


def test_log_push_provider_returns_true_and_logs():
    from app.services.push import LogPushProvider, get_push_provider

    provider = LogPushProvider()
    assert provider.send(123, "标题", "内容", {"invoice_id": 456}) is True
    assert isinstance(get_push_provider(), LogPushProvider)


# ═══════════════════════════════════════════════════════════════════════════════
# 卡 5436785c: get_push_provider 惰性初始化双检锁
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrentLazyInit:
    """多线程并发首调只构造一次 provider (双检锁, 同 wx_pay client 卡 692b3df7)。"""

    def test_concurrent_first_calls_init_once(self):
        """8 线程 Barrier 对齐后并发首调 → create_provider 仅构造一次。"""
        import app.services.push as push_module
        from app.services.push.log_provider import LogPushProvider

        push_module._provider = None  # reset

        call_count = {"n": 0}
        orig_create = push_module.create_provider

        def counting_create():
            call_count["n"] += 1
            time.sleep(0.05)  # 放大竞态窗口: 构造期间让其它线程抵达
            return orig_create()

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(push_module.get_push_provider())

        push_module.create_provider = counting_create
        try:
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            push_module.create_provider = orig_create
            push_module._provider = None  # 还原, 不污染其它测试

        assert len(results) == 8
        assert all(r is results[0] for r in results)  # 同一实例
        assert isinstance(results[0], LogPushProvider)
        assert call_count["n"] == 1  # 双检锁: 仅构造一次

    def test_set_push_provider_overrides_lock_init(self):
        """set_push_provider 覆盖后, get 直接返回注入实例 (不触构造)。"""
        import app.services.push as push_module
        from app.services.push.log_provider import LogPushProvider

        injected = LogPushProvider()
        push_module.set_push_provider(injected)
        try:
            call_count = {"n": 0}
            orig_create = push_module.create_provider
            push_module.create_provider = (
                lambda: call_count.update(n=call_count["n"] + 1) or orig_create()
            )
            try:
                assert push_module.get_push_provider() is injected
            finally:
                push_module.create_provider = orig_create
            assert call_count["n"] == 0
        finally:
            push_module._provider = None  # 还原


def test_invoice_app_push_uses_push_provider(monkeypatch, caplog):
    from app.services import invoice_notification as mod
    from app.services.push import LogPushProvider

    sent = []

    class Recorder(LogPushProvider):
        def send(self, end_user_id, title, body, payload):
            sent.append((end_user_id, title, body, payload))
            return True

    import app.services.push as push_module

    monkeypatch.setattr(push_module, "get_push_provider", lambda: Recorder())
    from app.models.invoice_request import InvoiceRequest

    request = InvoiceRequest(id=301, user_id=42, amount=77700)

    with caplog.at_level(logging.INFO, logger=mod.logger.name):
        mod._push_app_notification(request)

    assert sent == [
        (
            42,
            "发票开具通知",
            "您的开票申请已处理",
            {"invoice_id": 301, "amount": 77700},
        )
    ]
    assert any("APP-PUSH" in record.message for record in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# 卡 5a280e1a: resolve_device_targets — openid → end_users → device tokens
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveDeviceTargets:
    """按 openid 解析用户注册的 device tokens (best-effort, 永不抛)。"""

    def test_resolves_tokens_via_openid(self, db_session):
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.services.invoice_notification import resolve_device_targets

        u = EndUser(
            wx_openid="push-openid-1",
            nickname="",
            avatar_url="",
            user_type=EndUserType.APP,
            status=EndUserStatus.ACTIVE,
        )
        db_session.add(u)
        db_session.flush()
        db_session.add_all([
            EndUserDeviceToken(
                end_user_id=u.id, platform="ios", device_token="tok-ios"
            ),
            EndUserDeviceToken(
                end_user_id=u.id, platform="android", device_token="tok-and"
            ),
        ])
        db_session.commit()

        targets = resolve_device_targets(db_session, "push-openid-1")

        assert {t.device_token for t in targets} == {"tok-ios", "tok-and"}
        assert {t.platform for t in targets} == {"ios", "android"}

    def test_unknown_openid_returns_empty(self, db_session):
        from app.services.invoice_notification import resolve_device_targets

        assert resolve_device_targets(db_session, "no-such-openid") == []

    def test_none_openid_returns_empty(self, db_session):
        from app.services.invoice_notification import resolve_device_targets

        assert resolve_device_targets(db_session, None) == []

    def test_query_exception_returns_empty(self, monkeypatch, db_session):
        """查询异常 → 空列表, 不向上抛 (best-effort 契约)。"""
        from app.services.invoice_notification import resolve_device_targets

        def boom(*a, **kw):
            raise RuntimeError("db down")

        monkeypatch.setattr(db_session, "query", boom)
        assert resolve_device_targets(db_session, "any-openid") == []


# ═══════════════════════════════════════════════════════════════════════════════
# 卡 5a280e1a: _push_app_notification 按 device tokens 分发
# ═══════════════════════════════════════════════════════════════════════════════

class TestPushAppNotificationTokens:
    """按用户注册的 device tokens 逐个调 provider.send (无 token → 降级日志)。"""

    def _recorder(self):
        from app.services.push import LogPushProvider

        sent = []

        class Recorder(LogPushProvider):
            def send(self, end_user_id, title, body, payload):
                sent.append((end_user_id, title, body, payload))
                return True

        return Recorder(), sent

    def test_sends_per_device_token(self, client, monkeypatch):
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.models.invoice_request import InvoiceRequest
        from app.services import invoice_notification as mod

        s = client._sesh
        u = EndUser(
            wx_openid="push-openid-2",
            nickname="",
            avatar_url="",
            user_type=EndUserType.APP,
            status=EndUserStatus.ACTIVE,
        )
        s.add(u)
        s.flush()
        s.add_all([
            EndUserDeviceToken(end_user_id=u.id, platform="ios", device_token="t-ios"),
            EndUserDeviceToken(
                end_user_id=u.id, platform="android", device_token="t-and"
            ),
        ])
        s.commit()

        recorder, sent = self._recorder()
        import app.services.push as push_module

        monkeypatch.setattr(push_module, "get_push_provider", lambda: recorder)
        request = InvoiceRequest(id=302, user_id=42, amount=9900)

        mod._push_app_notification(request, db=s, openid="push-openid-2")

        assert [t[0] for t in sent] == [u.id, u.id]
        assert all(t[1] == "发票开具通知" for t in sent)
        assert {t[3].get("device_token") for t in sent} == {"t-ios", "t-and"}

    def test_no_tokens_falls_back_to_user_id_send(self, client, monkeypatch, caplog):
        """openid 解析不到 token → 降级: 仍调 provider.send(原 user_id 语义)。"""
        from app.models.invoice_request import InvoiceRequest
        from app.services import invoice_notification as mod

        recorder, sent = self._recorder()
        import app.services.push as push_module

        monkeypatch.setattr(push_module, "get_push_provider", lambda: recorder)
        request = InvoiceRequest(id=303, user_id=7, amount=100)

        with caplog.at_level(logging.DEBUG, logger=mod.logger.name):
            mod._push_app_notification(request, db=client._sesh, openid=None)

        assert sent == [
            (7, "发票开具通知", "您的开票申请已处理",
             {"invoice_id": 303, "amount": 100})
        ]
        assert any("无 device token" in r.message for r in caplog.records)

    def test_provider_send_error_does_not_raise(self, client, monkeypatch):
        """单 token 发送抛错 → 记日志继续, 不阻断其它 token 与主流程。"""
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.models.invoice_request import InvoiceRequest
        from app.services import invoice_notification as mod

        s = client._sesh
        u = EndUser(
            wx_openid="push-openid-3",
            nickname="",
            avatar_url="",
            user_type=EndUserType.APP,
            status=EndUserStatus.ACTIVE,
        )
        s.add(u)
        s.flush()
        s.add(EndUserDeviceToken(
            end_user_id=u.id, platform="ios", device_token="t1"
        ))
        s.add(EndUserDeviceToken(
            end_user_id=u.id, platform="android", device_token="t2"
        ))
        s.commit()

        from app.services.push import LogPushProvider

        calls = []

        class Flaky(LogPushProvider):
            def send(self, end_user_id, title, body, payload):
                calls.append(payload.get("device_token"))
                if payload.get("device_token") == "t1":
                    raise RuntimeError("provider boom")
                return True

        import app.services.push as push_module

        monkeypatch.setattr(push_module, "get_push_provider", lambda: Flaky())
        request = InvoiceRequest(id=304, user_id=9, amount=100)

        mod._push_app_notification(request, db=s, openid="push-openid-3")

        assert set(calls) == {"t1", "t2"}  # 抛错不阻断第二台设备


# ═══════════════════════════════════════════════════════════════════════════════
# 卡 5a280e1a: 端到端 — 运营开票 → openid 桥接 → 按 device tokens 分发
# ═══════════════════════════════════════════════════════════════════════════════

class TestIssueFlowPushesToDeviceTokens:
    """发票上传开具走完整通知链: payment_orders.openid → tokens → provider。"""

    def test_upload_issued_pushes_registered_tokens(self, client, monkeypatch):
        import bcrypt
        from app.models.charging_order import (
            ChargingOrder, OrderPaymentStatus, OrderStatus, UserType, PaymentMethod,
        )
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.models.payment_order import PaymentOrder, PayScene, PaymentStatus
        from app.models.station import Station, StationStatus
        from app.models.user import User, UserRole, Team

        s = client._sesh
        team = Team(name="推送链路团队", code="PUSHT")
        s.add(team)
        s.flush()
        user = User(
            username="push_flow_user", real_name="推送链路用户",
            role=UserRole.VIEWER,
            team_id=team.id, status="active",
            password_hash=bcrypt.hashpw(b"pw123456", bcrypt.gensalt()).decode(),
        )
        s.add(user)
        station = Station(
            name="推送链路站", code="PUSHS", team_id=team.id,
            status=StationStatus.NORMAL,
        )
        s.add(station)
        s.flush()
        device = Device(
            sn="PUSHSN01", name="推送链路桩", code="PUSHD",
            station_id=station.id,
            type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
            rated_power=120.0,
        )
        s.add(device)
        s.flush()

        order_no = "PUSH_ORD_001"
        order = ChargingOrder(
            order_no=order_no,
            station_id=station.id,
            device_id=device.id,
            user_id=user.id,
            user_type=UserType.APP,
            paid_amount=66,
            total_amount=66,
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        )
        s.add(order)

        # IM-B支付单带 openid → 通知钩子桥接 end_users → device tokens
        s.add(PaymentOrder(
            out_trade_no="PUSH_PO_001",
            business_order_no=order_no,
            openid="push-flow-openid",
            scene=PayScene.MINIPROGRAM,
            sub_mchid="sub-mch",
            amount_fen=6600,
            payment_status=PaymentStatus.PAID,
        ))

        end_user = EndUser(
            wx_openid="push-flow-openid",
            nickname="",
            avatar_url="",
            user_type=EndUserType.APP,
            status=EndUserStatus.ACTIVE,
        )
        s.add(end_user)
        s.flush()
        s.add_all([
            EndUserDeviceToken(
                end_user_id=end_user.id, platform="ios", device_token="e2e-ios"
            ),
        ])
        s.commit()

        login = client.post(
            "/api/v1/auth/login",
            data={"username": "push_flow_user", "password": "pw123456"},
        )
        token = login.json()["data"]["token"]
        apply_r = client.post(
            "/api/v1/business/invoices",
            json={"order_ids": [order_no], "title_type": "personal",
                  "title_name": "李四"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert apply_r.status_code == 202, apply_r.text
        invoice_id = apply_r.json()["data"]["invoice_id"]

        from app.services.push import LogPushProvider

        sent = []

        class Recorder(LogPushProvider):
            def send(self, end_user_id, title, body, payload):
                sent.append(payload)
                return True

        import app.services.push as push_module

        monkeypatch.setattr(push_module, "get_push_provider", lambda: Recorder())

        # 运营 (client 默认 admin) 上传发票 → ISSUED → 通知钩子
        up = client.post(
            f"/api/v1/ops/invoice-requests/{invoice_id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4\nfake", "application/pdf")},
        )
        assert up.status_code == 200, up.text

        token_payloads = [p for p in sent if p.get("device_token")]
        assert token_payloads == [{
            "invoice_id": invoice_id,
            "amount": 6600,
            "device_token": "e2e-ios",
            "platform": "ios",
            # 卡 7f601f7f: payload 增补 status (契约 v1.3 小写终态)
            "status": "issued",
        }]
