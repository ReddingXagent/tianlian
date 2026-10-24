#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志服务测试
"""
import logging
from unittest.mock import MagicMock

import pytest
from app.services.audit_service import AuditService
from app.models.audit_log import AuditLog


class TestAuditService:
    def test_service_initialization(self):
        service = AuditService()
        assert service is not None

    def test_service_has_log_method(self):
        service = AuditService()
        assert hasattr(service, "log")
        assert callable(service.log)

    def test_service_has_get_logs_method(self):
        service = AuditService()
        assert hasattr(service, "get_logs")
        assert callable(service.get_logs)

    def test_service_has_get_stats_method(self):
        service = AuditService()
        assert hasattr(service, "get_stats")
        assert callable(service.get_stats)

    def test_log_with_test_db(self, test_db):
        """使用测试数据库记录审计日志"""
        service = AuditService()
        db = test_db["SessionLocal"]()
        result = service.log(
            db=db,
            user_id=1,
            username="admin",
            action="login",
            module="auth",
            detail="测试日志",
        )
        db.close()
        assert result is not None
        assert result.id is not None
        assert result.username == "admin"

    def test_get_logs_returns_dict(self, test_db):
        """get_logs 返回字典"""
        service = AuditService()
        db = test_db["SessionLocal"]()
        logs = service.get_logs(page=1, page_size=10, db=db)
        db.close()
        assert isinstance(logs, dict)
        assert "items" in logs
        assert "total" in logs

    def test_log_and_query_roundtrip(self, test_db):
        """记录日志后能查询到"""
        service = AuditService()
        db = test_db["SessionLocal"]()

        # 记录一条日志
        service.log(
            db=db,
            user_id=1,
            username="admin",
            action="create",
            module="devices",
            target_id="42",
            detail="创建设备",
            ip_address="127.0.0.1",
        )

        # 查询
        result = service.get_logs(page=1, page_size=10, db=db)
        assert result["total"] == 1
        assert result["items"][0]["username"] == "admin"
        assert result["items"][0]["action"] == "create"
        db.close()

    def test_log_crud(self, test_db):
        """log_crud 方法正常工作"""
        service = AuditService()
        db = test_db["SessionLocal"]()
        result = service.log_crud(
            db=db,
            user_id=1,
            username="admin",
            action="update",
            module="stations",
            target_id="5",
            target_desc="更新电站 #5",
            detail="修改电站名称",
        )
        db.close()
        assert result is not None
        assert result.action == "update"

    def test_log_login(self, test_db):
        """log_login 方法正常工作"""
        service = AuditService()
        db = test_db["SessionLocal"]()
        result = service.log_login(
            db=db,
            user_id=1,
            username="admin",
            ip="192.168.1.1",
            success=True,
        )
        db.close()
        assert result is not None
        assert result.action == "login"
        assert result.result == "success"

    def test_get_stats_with_data(self, test_db):
        """有数据时统计正常"""
        service = AuditService()
        db = test_db["SessionLocal"]()

        # 记录多条日志
        for i in range(5):
            service.log(
                db=db,
                user_id=1,
                username="admin",
                action="login" if i % 2 == 0 else "create",
                module="auth" if i % 2 == 0 else "devices",
            )

        stats = service.get_stats(db=db)
        assert stats["total_logs"] == 5
        assert "by_action" in stats
        assert "by_module" in stats
        db.close()

    def test_filter_by_action(self, test_db):
        """按操作类型筛选"""
        service = AuditService()
        db = test_db["SessionLocal"]()

        service.log(db=db, user_id=1, username="admin", action="login", module="auth")
        service.log(db=db, user_id=1, username="admin", action="create", module="devices")
        service.log(db=db, user_id=1, username="admin", action="delete", module="stations")

        result = service.get_logs(page=1, page_size=10, action="login", db=db)
        assert result["total"] == 1
        assert result["items"][0]["action"] == "login"
        db.close()

    def test_filter_by_module(self, test_db):
        """按模块筛选"""
        service = AuditService()
        db = test_db["SessionLocal"]()

        service.log(db=db, user_id=1, username="admin", action="create", module="devices")
        service.log(db=db, user_id=1, username="admin", action="update", module="stations")

        result = service.get_logs(page=1, page_size=10, module="devices", db=db)
        assert result["total"] == 1
        assert result["items"][0]["module"] == "devices"
        db.close()

    def test_filter_by_username(self, test_db):
        """按用户名筛选"""
        service = AuditService()
        db = test_db["SessionLocal"]()

        service.log(db=db, user_id=1, username="admin", action="login", module="auth")
        service.log(db=db, user_id=2, username="engineer1", action="login", module="auth")

        result = service.get_logs(page=1, page_size=10, username="engineer1", db=db)
        assert result["total"] == 1
        assert result["items"][0]["username"] == "engineer1"
        db.close()


class TestAuditFailureSafety:
    """审计失败必须静默兜底（不抛 + 回滚 + 留 ERROR 痕迹），业务零感知。"""

    @staticmethod
    def _broken_session() -> MagicMock:
        """构造一个 commit 抛异常的 session，模拟审计写入失败。"""
        session = MagicMock()
        session.commit.side_effect = RuntimeError("audit db down")
        return session

    def test_log_failure_does_not_raise_and_logs_error(self, caplog):
        """log() 写入失败: 不抛 + 返回 None + rollback + 留 ERROR 日志"""
        service = AuditService()
        session = self._broken_session()
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            result = service.log(
                db=session,
                user_id=1,
                username="admin",
                action="create",
                module="devices",
                target_id="42",
            )
        assert result is None
        session.rollback.assert_called_once()
        assert any(
            "审计日志写入失败" in r.getMessage() and r.levelno >= logging.ERROR
            for r in caplog.records
        )

    def test_log_crud_failure_does_not_raise(self, caplog):
        """log_crud 链路失败: 不抛 + 留痕"""
        service = AuditService()
        session = self._broken_session()
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            result = service.log_crud(
                db=session,
                user_id=1,
                username="admin",
                action="update",
                module="stations",
                target_id="5",
            )
        assert result is None
        session.rollback.assert_called_once()
        assert any(
            "审计日志写入失败" in r.getMessage() for r in caplog.records
        )

    def test_log_login_failure_does_not_raise(self, caplog):
        """log_login 链路失败: 不抛 + 留痕"""
        service = AuditService()
        session = self._broken_session()
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            result = service.log_login(db=session, user_id=1, username="admin")
        assert result is None
        session.rollback.assert_called_once()
        assert any(
            "审计日志写入失败" in r.getMessage() for r in caplog.records
        )

    def test_log_crud_success_returns_auditlog(self, test_db):
        """正常路径: log_crud 返回 AuditLog 实例"""
        service = AuditService()
        db = test_db["SessionLocal"]()
        result = service.log_crud(
            db=db,
            user_id=1,
            username="admin",
            action="create",
            module="devices",
            target_id="7",
            target_desc="创建设备",
        )
        db.close()
        assert isinstance(result, AuditLog)
        assert result.action == "create"
        assert result.module == "devices"
        assert result.target_id == "7"

    def test_tenant_endpoint_succeeds_when_audit_fails(self, client, monkeypatch):
        """审计彻底失败时，创建租户端点仍成功（业务零感知）。

        通过给 audit_service 注入坏 session，让真实 log/log_crud 跑到失败分支
        （返回 None + 留痕），验证端点既有的 try/except 兜底仍生效。
        """
        import app.services.audit_service as audit_mod

        monkeypatch.setattr(
            audit_mod.AuditService,
            "_get_db",
            lambda self, db=None: MagicMock(commit=MagicMock(side_effect=RuntimeError("audit down"))),
        )

        resp = client.post(
            "/api/v1/tenants",
            json={"name": "审计失败租户", "code": "AUDIT_FAIL_001"},
        )
        assert resp.status_code == 200, f"审计失败不应阻断业务: {resp.text}"

    def test_user_endpoint_succeeds_when_audit_fails(self, client, monkeypatch):
        """审计彻底失败时，创建用户端点仍成功（业务零感知）。"""
        import app.services.audit_service as audit_mod

        monkeypatch.setattr(
            audit_mod.AuditService,
            "_get_db",
            lambda self, db=None: MagicMock(commit=MagicMock(side_effect=RuntimeError("audit down"))),
        )

        resp = client.post(
            "/api/v1/users",
            json={"username": "audit_fail_user", "password": "p123456", "real_name": "审计失败用户"},
        )
        assert resp.status_code == 200, f"审计失败不应阻断业务: {resp.text}"
