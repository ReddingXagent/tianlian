"""
站内消息中心 (Notifications Inbox) — admin-platform-spec §2.8

覆盖:
- 发送站内消息 → 收件箱能查到 (含发送侧集成: /send 站内渠道落 Notification)
- 未读数正确 (发2 → 2, 读1 → 1)
- 标记已读: is_read=True + read_at 非空
- 全部已读 → 未读数=0
- 隔离: A 团队角色广播消息 B 团队看不到 (team_id 隔离键)
- unread_only 过滤: 只返未读

隔离契约: 与 Station.team_id / operations_analytics._team_scope 同 — admin 平台级全可见,
团队级用户只看本团队 + 平台广播(NULL)。User 无 tenant_id (已注释), 故隔离键用 team_id。
"""
from datetime import datetime, timezone

import bcrypt
import pytest

from app.models.notification import Notification
from app.models.user import Team, User, UserRole


# ─────────────────────────────────────────────────────────
#  helpers
# ─────────────────────────────────────────────────────────

def _user_token(client, username: str, password: str) -> str:
    """登录指定用户拿 JWT。"""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _send_inbox(client, user_id, title, content="c"):
    """以 admin 身份向 user_id 发一条站内消息 (走 /send 集成路径)。"""
    r = client.post(
        "/api/v1/notifications/send",
        json={
            "user_id": str(user_id),
            "title": title,
            "content": content,
            "channel": "app_push",
        },
    )
    assert r.status_code == 200, f"发送失败: {r.text}"


@pytest.fixture(scope="function")
def inbox_users(client):
    """两个分属不同团队的用户: alice@团队Alpha, bob@团队Beta (均 engineer)。"""
    s = client._sesh
    t_a = Team(name="团队Alpha", code="ALPHA")
    t_b = Team(name="团队Beta", code="BETA")
    s.add_all([t_a, t_b])
    s.commit()
    s.refresh(t_a)
    s.refresh(t_b)

    def add(username, password, team):
        u = User(
            username=username,
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            role=UserRole.ENGINEER,
            status="active",
            team_id=team.id,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return u

    alice = add("alice", "alice123", t_a)
    bob = add("bob", "bob123", t_b)
    return {"alice": alice, "bob": bob, "team_a": t_a, "team_b": t_b}


# ─────────────────────────────────────────────────────────
#  用例
# ─────────────────────────────────────────────────────────

def test_send_then_inbox(client, inbox_users):
    """发送站内消息 → 收件箱能查到。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "你好Alice", content="欢迎")

    tok = _user_token(client, "alice", "alice123")
    r = client.get("/api/v1/notifications/inbox", headers=_auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 1
    titles = [it["title"] for it in data["items"]]
    assert "你好Alice" in titles


def test_unread_count(client, inbox_users):
    """发2条 → 未读2；读1条 → 未读1。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "m1")
    _send_inbox(client, alice.id, "m2")

    tok = _user_token(client, "alice", "alice123")
    r = client.get("/api/v1/notifications/unread-count", headers=_auth(tok))
    assert r.json()["data"]["unread_count"] == 2

    inbox = client.get("/api/v1/notifications/inbox", headers=_auth(tok)).json()["data"]
    nid = inbox["items"][0]["id"]
    rr = client.post(f"/api/v1/notifications/{nid}/read", headers=_auth(tok))
    assert rr.status_code == 200

    r = client.get("/api/v1/notifications/unread-count", headers=_auth(tok))
    assert r.json()["data"]["unread_count"] == 1


def test_mark_read_sets_flag(client, inbox_users):
    """标记已读后 is_read=True + read_at 非空。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "待读")

    tok = _user_token(client, "alice", "alice123")
    inbox = client.get("/api/v1/notifications/inbox", headers=_auth(tok)).json()["data"]
    item = inbox["items"][0]
    assert item["is_read"] is False
    nid = item["id"]

    rr = client.post(f"/api/v1/notifications/{nid}/read", headers=_auth(tok))
    assert rr.status_code == 200

    inbox2 = client.get("/api/v1/notifications/inbox", headers=_auth(tok)).json()["data"]
    after = next(it for it in inbox2["items"] if it["id"] == nid)
    assert after["is_read"] is True
    assert after["read_at"] is not None


def test_read_all(client, inbox_users):
    """全部标记已读 → 未读数=0。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "m1")
    _send_inbox(client, alice.id, "m2")

    tok = _user_token(client, "alice", "alice123")
    rr = client.post("/api/v1/notifications/read-all", headers=_auth(tok))
    assert rr.status_code == 200

    r = client.get("/api/v1/notifications/unread-count", headers=_auth(tok))
    assert r.json()["data"]["unread_count"] == 0


def test_read_all_sets_read_at_on_all(client, inbox_users):
    """全部已读后: 未读数=0 且每条 read_at 非空 (bulk UPDATE 契约)。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "m1")
    _send_inbox(client, alice.id, "m2")

    tok = _user_token(client, "alice", "alice123")
    rr = client.post("/api/v1/notifications/read-all", headers=_auth(tok))
    assert rr.status_code == 200
    assert rr.json()["data"]["marked_count"] == 2

    r = client.get("/api/v1/notifications/unread-count", headers=_auth(tok))
    assert r.json()["data"]["unread_count"] == 0

    inbox = client.get("/api/v1/notifications/inbox", headers=_auth(tok)).json()["data"]
    assert inbox["total"] == 2
    assert all(it["is_read"] is True and it["read_at"] for it in inbox["items"])


def test_read_all_does_not_touch_other_users(client, inbox_users):
    """alice 全部已读不影响 bob: 跨用户 scope 隔离 (bulk UPDATE 下推 scope 条件)。"""
    alice, bob = inbox_users["alice"], inbox_users["bob"]
    _send_inbox(client, alice.id, "给alice")
    _send_inbox(client, bob.id, "给bob")

    alice_tok = _user_token(client, "alice", "alice123")
    rr = client.post("/api/v1/notifications/read-all", headers=_auth(alice_tok))
    assert rr.status_code == 200

    bob_tok = _user_token(client, "bob", "bob123")
    r = client.get("/api/v1/notifications/unread-count", headers=_auth(bob_tok))
    assert r.json()["data"]["unread_count"] == 1


def test_team_isolation(client, inbox_users):
    """A 团队的角色广播消息 B 团队看不到 (team_id 隔离键)。"""
    s = client._sesh
    t_a = inbox_users["team_a"]
    t_b = inbox_users["team_b"]
    # 两条 engineer 角色广播: alice/bob 都是 engineer, 都命中 recipient; 靠 team_id 区分
    s.add_all([
        Notification(
            title="A团队广播", content="c", type="system", sender="system",
            recipient_type="role", recipient_id="engineer", channel="app_push",
            status="sent", sent_at=datetime.now(timezone.utc), team_id=t_a.id,
        ),
        Notification(
            title="B团队广播", content="c", type="system", sender="system",
            recipient_type="role", recipient_id="engineer", channel="app_push",
            status="sent", sent_at=datetime.now(timezone.utc), team_id=t_b.id,
        ),
    ])
    s.commit()

    alice_tok = _user_token(client, "alice", "alice123")
    bob_tok = _user_token(client, "bob", "bob123")
    a_titles = [
        it["title"]
        for it in client.get("/api/v1/notifications/inbox", headers=_auth(alice_tok)).json()["data"]["items"]
    ]
    b_titles = [
        it["title"]
        for it in client.get("/api/v1/notifications/inbox", headers=_auth(bob_tok)).json()["data"]["items"]
    ]
    assert "A团队广播" in a_titles
    assert "B团队广播" not in a_titles
    assert "B团队广播" in b_titles
    assert "A团队广播" not in b_titles


def test_null_team_not_broadcast_to_team_users(client, inbox_users):
    """team_id IS NULL 的消息不对团队级用户广播 (严格隔离: NULL 仅匹配 NULL)。

    对齐 deps._team_denied 契约——避免「未分配 team」与「团队用户」的越权模糊地带。
    admin 才可见平台级(NULL)消息。
    """
    s = client._sesh
    s.add(Notification(
        title="NULL团队系统消息", content="c", type="system", sender="system",
        recipient_type="role", recipient_id="engineer", channel="app_push",
        status="sent", sent_at=datetime.now(timezone.utc), team_id=None,
    ))
    s.commit()

    # alice (engineer, team_a) 不应看到 NULL-team 消息
    alice_tok = _user_token(client, "alice", "alice123")
    a_titles = [
        it["title"]
        for it in client.get("/api/v1/notifications/inbox", headers=_auth(alice_tok)).json()["data"]["items"]
    ]
    assert "NULL团队系统消息" not in a_titles


def test_unread_only_filter(client, inbox_users):
    """unread_only=true 只返未读。"""
    alice = inbox_users["alice"]
    _send_inbox(client, alice.id, "m1")
    _send_inbox(client, alice.id, "m2")

    tok = _user_token(client, "alice", "alice123")
    inbox = client.get("/api/v1/notifications/inbox", headers=_auth(tok)).json()["data"]
    nid = inbox["items"][0]["id"]
    client.post(f"/api/v1/notifications/{nid}/read", headers=_auth(tok))

    r = client.get("/api/v1/notifications/inbox?unread_only=true", headers=_auth(tok))
    data = r.json()["data"]
    assert data["total"] == 1
    assert all(it["is_read"] is False for it in data["items"])
