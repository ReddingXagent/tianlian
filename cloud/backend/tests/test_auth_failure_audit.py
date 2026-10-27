"""
登录失败分支补审计日志 (卡 69142d4e)

背景: commit 44fa4e8f6 后 GET /security/threats 从 audit_logs 派生
(module=auth & result=failure), 但 log_login 只在登录成功路径调用 →
密码错误/用户不存在/423锁定三类失败分支不写审计, 生产 /threats 恒空。

契约:
- 三类失败分支各写一条 failure 审计 (user_not_found 可无 user_id)
- 用户可见响应不因用户存在与否而变 (防用户名枚举): 401 detail 全等
- 审计内部 error_msg 区分 user_not_found / wrong_password / locked
- 审计写入失败不改变登录响应 (audit_service.log 内部吞异常, 卡 be2dbf042)
"""
import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog


def _failed_rows(db, *, username=None):
    """查 failure 登录审计记录 (排除成功登录)。"""
    q = db.query(AuditLog).filter(
        AuditLog.module == "auth",
        AuditLog.action == "login",
        AuditLog.result == "failure",
    )
    if username is not None:
        q = q.filter(AuditLog.username == username)
    return q.all()


def _login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )


class TestFailureAudit:
    """三类失败分支的审计写入"""

    def test_wrong_password_writes_failure_audit(self, client, seed_users):
        """密码错误 → 401 + audit_logs 出现 failure 记录, 带 ip 与 error_msg"""
        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()

        r = _login(client, "admin", "definitely-wrong-password")
        assert r.status_code == 401

        s.expire_all()
        rows = _failed_rows(s, username="admin")
        assert len(rows) == 1, f"应写1条失败审计, 实际 {len(rows)}"
        row = rows[0]
        assert row.user_id is not None, "已存在用户失败应带 user_id"
        assert row.ip_address, "失败审计应记录来源 IP"
        assert row.error_msg, "失败审计应有 error_msg 区分原因"

    def test_user_not_found_writes_failure_audit(self, client, seed_users):
        """用户不存在 → 401 + 审计记录 (user_id 可空, username 记录尝试名)"""
        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()

        r = _login(client, "ghost-user-404", "whatever")
        assert r.status_code == 401

        s.expire_all()
        rows = _failed_rows(s, username="ghost-user-404")
        assert len(rows) == 1, f"应写1条失败审计, 实际 {len(rows)}"
        assert rows[0].user_id is None, "不存在的用户无 user_id, 应为 NULL"
        assert rows[0].error_msg

    def test_locked_account_writes_failure_audit(self, client, seed_users):
        """423 锁定分支 → 审计记录, error_msg 标记 locked"""
        from datetime import datetime, timedelta, timezone
        from app.models.user import User

        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()
        user = s.query(User).filter(User.username == "admin").first()
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        s.commit()

        r = _login(client, "admin", "admin123")
        assert r.status_code == 423

        s.expire_all()
        rows = _failed_rows(s, username="admin")
        assert len(rows) == 1, f"锁定分支应写1条审计, 实际 {len(rows)}"
        assert "locked" in (rows[0].error_msg or ""), (
            f"锁定审计 error_msg 应含 locked, 实际: {rows[0].error_msg}"
        )

    def test_no_username_enumeration_in_response(self, client, seed_users):
        """防用户名枚举: 用户不存在的 401 detail 与密码错误完全一致"""
        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()

        r1 = _login(client, "admin", "wrong-password")
        r2 = _login(client, "no-such-user", "wrong-password")
        assert r1.status_code == r2.status_code == 401
        assert r1.json()["detail"] == r2.json()["detail"], (
            "失败提示语不得因用户存在与否而变 (防枚举)"
        )

    def test_audit_write_failure_does_not_change_response(self, client, seed_users, monkeypatch):
        """审计写入异常被吞掉, 登录失败响应不受影响"""
        from app.services.audit_service import audit_service

        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()

        def _boom(*a, **kw):
            raise RuntimeError("audit backend down")

        monkeypatch.setattr(audit_service, "log_login", _boom)

        r = _login(client, "admin", "wrong-password")
        assert r.status_code == 401, "审计故障不应改变登录失败响应"


class TestThreatsDerivedFromFailures:
    """端到端: 失败登录 → audit_logs → GET /security/threats"""

    def test_failed_login_visible_in_threats(self, client, seed_users):
        """真实失败登录产生的事件能被 /threats 查到"""
        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()

        r = _login(client, "admin", "wrong-password-x")
        assert r.status_code == 401

        body = client.get("/api/v1/security/threats").json()["data"]
        assert body["total"] == 1, f"/threats 应查到1条, 实际 {body['total']}"
        item = body["items"][0]
        assert item["type"] == "brute_force"
        assert item["target"] == "admin"
        assert item["source_ip"], "威胁事件应带来源 IP"

    def test_lockout_locking_attempt_visible_in_threats(self, client, seed_users):
        """5 次错误触发锁定后, /threats 聚合出该 (ip, username) 的爆破威胁"""
        from datetime import datetime, timedelta, timezone
        from app.models.user import User

        s = client._sesh
        s.query(AuditLog).delete()
        s.commit()
        user = s.query(User).filter(User.username == "admin").first()
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        s.commit()

        r = _login(client, "admin", "admin123")  # 锁定分支
        assert r.status_code == 423

        body = client.get("/api/v1/security/threats").json()["data"]
        assert body["total"] == 1
        assert body["items"][0]["target"] == "admin"
