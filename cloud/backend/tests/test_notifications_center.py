"""
消息中心 API 测试 — 覆盖 templates / messages / stats 三类端点

对齐前端 MessageCenter(index.tsx) 实际消费的字段与响应结构：
  - GET    /notifications/templates  -> paginated {items, total, page, page_size}
  - POST   /notifications/templates
  - PUT    /notifications/templates/{id}
  - DELETE /notifications/templates/{id}
  - GET    /notifications/messages   -> paginated，支持 status/channel 筛选
  - DELETE /notifications/messages/{id}
  - GET    /notifications/stats      -> {total_templates, total_messages, sent_today,
                                       failed_count, channel_distribution}
"""
from app.models.notification_config import NotificationTemplate, NotificationLog


# ──────────────── 模板 CRUD ────────────────

def test_create_template_returns_frontend_fields(client):
    """POST /templates 返回前端契约字段（template_type/title/channels）"""
    resp = client.post("/api/v1/notifications/templates", json={
        "name": "充电完成通知",
        "template_type": "charging",
        "title": "{station_name} 充电完成通知",
        "content": "您的车辆在 {station_name} 已充电完成",
        "channels": ["sms", "app_push"],
        "variables": [{"name": "station_name", "desc": "电站名"}],
        "enabled": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["id"]
    assert data["name"] == "充电完成通知"
    assert data["template_type"] == "charging"
    assert data["title"] == "{station_name} 充电完成通知"
    assert "充电完成" in data["content"]
    assert data["channels"] == ["sms"]          # 复用单 channel 列，取首个
    assert data["enabled"] is True
    assert data["created_at"]


def test_list_templates_paginated(client):
    """GET /templates 返回分页结构，items 含前端字段"""
    for i in range(3):
        client.post("/api/v1/notifications/templates", json={
            "name": f"模板{i}",
            "template_type": "system",
            "title": f"标题{i}",
            "content": f"内容{i}",
            "channels": ["email"],
        })
    resp = client.get("/api/v1/notifications/templates", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) >= {"items", "total", "page", "page_size"}
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["template_type"]


def test_update_template(client):
    """PUT /templates/{id} 更新字段"""
    create = client.post("/api/v1/notifications/templates", json={
        "name": "旧模板", "template_type": "system",
        "title": "旧标题", "content": "旧内容", "channels": ["sms"],
    }).json()["data"]
    resp = client.put(f"/api/v1/notifications/templates/{create['id']}", json={
        "name": "新模板", "title": "新标题", "enabled": False,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "新模板"
    assert data["title"] == "新标题"
    assert data["enabled"] is False


def test_delete_template(client):
    """DELETE /templates/{id} 删除后列表不再包含"""
    create = client.post("/api/v1/notifications/templates", json={
        "name": "待删", "template_type": "custom", "content": "x", "channels": [],
    }).json()["data"]
    resp = client.delete(f"/api/v1/notifications/templates/{create['id']}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
    lst = client.get("/api/v1/notifications/templates").json()["data"]
    assert all(it["id"] != create["id"] for it in lst["items"])


def test_update_template_not_found(client):
    """异常路径：更新不存在的模板返回 404"""
    resp = client.put("/api/v1/notifications/templates/999999", json={"name": "x"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "模板不存在"


def test_delete_template_not_found(client):
    """异常路径：删除不存在的模板返回 404"""
    resp = client.delete("/api/v1/notifications/templates/999999")
    assert resp.status_code == 404


def test_create_template_missing_required(client):
    """异常路径：缺必填字段 content 返回 422"""
    resp = client.post("/api/v1/notifications/templates", json={"name": "无内容"})
    assert resp.status_code == 422


# ──────────────── 消息记录 ────────────────

def _seed_log(db, *, channel="app_push", status="sent", receiver="user:001", template_id=None):
    """直接向 NotificationLog 插入一条记录（send 端点为骨架不写日志）"""
    log = NotificationLog(
        event_type="manual",
        channel=channel,
        template_id=template_id,
        receiver_type="user",
        receiver_id=receiver,
        subject="测试消息标题",
        content="测试消息正文",
        status=status,
        sent_at=None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def test_list_messages_pagination_and_filter(client, db_session):
    """GET /messages 分页 + status/channel 筛选，字段对齐前端"""
    _seed_log(db_session, channel="sms", status="sent")
    _seed_log(db_session, channel="app_push", status="failed")
    _seed_log(db_session, channel="app_push", status="sent")

    resp = client.get("/api/v1/notifications/messages", params={"page": 1, "page_size": 20})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3
    item = data["items"][0]
    # 前端消费字段
    assert {"id", "title", "channel", "status", "receivers", "sender",
            "sent_at", "result_message"} <= set(item.keys())
    assert isinstance(item["receivers"], list)

    # 渠道筛选
    r_ch = client.get("/api/v1/notifications/messages", params={"channel": "app_push"}).json()["data"]
    assert r_ch["total"] == 2
    assert all(it["channel"] == "app_push" for it in r_ch["items"])

    # 状态筛选
    r_st = client.get("/api/v1/notifications/messages", params={"status": "failed"}).json()["data"]
    assert r_st["total"] == 1
    assert r_st["items"][0]["status"] == "failed"


def test_list_messages_template_name_join(client, db_session):
    """消息记录的 template_name 通过 template_id 关联模板名"""
    tpl = client.post("/api/v1/notifications/templates", json={
        "name": "关联模板", "template_type": "system", "content": "c", "channels": ["sms"],
    }).json()["data"]
    _seed_log(db_session, channel="sms", status="sent", template_id=tpl["id"])
    data = client.get("/api/v1/notifications/messages").json()["data"]
    assert data["items"][0]["template_name"] == "关联模板"
    assert data["items"][0]["template_id"] == tpl["id"]


def test_delete_message(client, db_session):
    """DELETE /messages/{id} 删除成功"""
    log = _seed_log(db_session, status="sent")
    resp = client.delete(f"/api/v1/notifications/messages/{log.id}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
    assert client.get("/api/v1/notifications/messages").json()["data"]["total"] == 0


def test_delete_message_not_found(client):
    """异常路径：删除不存在的消息记录返回 404"""
    resp = client.delete("/api/v1/notifications/messages/999999")
    assert resp.status_code == 404


# ──────────────── 统计 ────────────────

def test_stats_aggregation(client, db_session):
    """GET /stats 聚合：模板数/消息数/失败数/渠道分布"""
    from datetime import datetime
    from sqlalchemy import update
    from app.tasks.tz_utils import today_in_biz_tz
    client.post("/api/v1/notifications/templates", json={
        "name": "T1", "template_type": "system", "content": "c", "channels": ["sms"],
    })
    _seed_log(db_session, channel="sms", status="sent")
    _seed_log(db_session, channel="app_push", status="failed")
    _seed_log(db_session, channel="app_push", status="sent")

    # sent_today 口径改业务日 (卡 ba16a9ff): created_at 为 server_default 当前 UTC 时刻,
    # 上海 16:00-24:00 窗口 UTC 日=业务昨天会漏计 → seed 显式钉到业务今天 UTC 日内
    # (日期敏感腐烂, 翻转 seed 非断言)。
    biz_today = today_in_biz_tz()
    db_session.execute(update(NotificationLog)
                       .values(created_at=datetime(biz_today.year, biz_today.month,
                                                   biz_today.day, 12, 0)))
    db_session.commit()

    resp = client.get("/api/v1/notifications/stats")
    assert resp.status_code == 200
    s = resp.json()["data"]
    assert s["total_templates"] == 1
    assert s["total_messages"] == 3
    assert s["failed_count"] == 1
    assert s["sent_today"] == 3                      # 业务当天创建
    assert s["channel_distribution"]["sms"] == 1
    assert s["channel_distribution"]["app_push"] == 2


def test_stats_empty(client):
    """空库下 stats 返回零值结构，不报错"""
    s = client.get("/api/v1/notifications/stats").json()["data"]
    assert s["total_templates"] == 0
    assert s["total_messages"] == 0
    assert s["failed_count"] == 0
    assert s["channel_distribution"] == {}


# ──────────────── send 端点回归（不被破坏） ────────────────

def test_send_notification_still_works(client):
    """既有 POST /send 端点未被破坏"""
    resp = client.post("/api/v1/notifications/send", json={
        "user_id": "u-x", "title": "t", "content": "c", "channel": "app",
    })
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
